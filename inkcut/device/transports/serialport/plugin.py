# -*- coding: utf-8 -*-
"""
Copyright (c) 2017-2019, Jairus Martin.

Distributed under the terms of the GPL v3 License.

The full license is in the file LICENSE, distributed with this software.

Created on Jul 12, 2015

@author: jrm
"""
import serial
import traceback
from atom.atom import set_default
from atom.api import List, Instance, Enum, Bool, Int, Str
from inkcut.core.api import Plugin, Model, log
from inkcut.device.plugin import DeviceTransport
from twisted.internet import reactor
from twisted.internet.protocol import Protocol, connectionDone
from twisted.internet.serialport import SerialPort
from serial.tools.list_ports import comports
import re

from inkcut.device.transports.raw.plugin import RawFdTransport, RawFdProtocol

class SerialPortInfo(Model):
    device_path = Str()
    description = Str()
    usb_pid = Int()
    usb_vid = Int()

    def __str__(self):
        return self.description


class SerialConfigBase(Model):
    #: Available serial ports
    ports = List()

    #: Serial port config
    port = Str().tag(config=True)

    port_filter_name = Str().tag(config=True)
    port_filter_vid = Int().tag(config=True)
    port_filter_pid = Int().tag(config=True)

    baudrate = Int(9600).tag(config=True)
    bytesize = Enum(serial.EIGHTBITS, serial.SEVENBITS, serial.SIXBITS,
                    serial.FIVEBITS).tag(config=True)
    parity = Enum(*serial.PARITY_NAMES.keys()).tag(config=True)
    stopbits = Enum(serial.STOPBITS_ONE, serial.STOPBITS_ONE_POINT_FIVE,
                    serial.STOPBITS_TWO).tag(config=True)
    xonxoff = Bool().tag(config=True)
    rtscts = Bool().tag(config=True)
    dsrdtr = Bool().tag(config=True)

    # -------------------------------------------------------------------------
    # Defaults
    # -------------------------------------------------------------------------
    def _default_ports(self):
        return []

    def _default_parity(self):
        return 'N'

    def _default_port(self):
        if self.ports:
            return self.ports[0].device_path
        return ""

    def refresh(self):
        self.ports = self._default_ports()

    def has_port_filter(self):
        return self.port_filter_name != "" or self.port_filter_vid > 0 or self.port_filter_pid > 0

    def port_matches(self, port: SerialPortInfo):
        if self.port_filter_name:
            if not re.search(self.port_filter_name, port.description):
                return False
        if self.port_filter_vid > 0 and port.usb_vid != self.port_filter_vid:
            return False
        if self.port_filter_pid > 0 and port.usb_pid != self.port_filter_pid:
            return False
        return True

    def clear_filter(self):
        self.port_filter_name = ""
        self.port_filter_vid = 0
        self.port_filter_pid = 0

    def make_filter(self, port_info: SerialPortInfo):
        self.clear_filter()
        if not port_info:
            return
        if port_info.usb_vid > 0:
            # usb devices should have both vid and pid
            self.port_filter_vid = port_info.usb_vid
            self.port_filter_pid = port_info.usb_pid

            # For now assume that only usb devices will have a meaningful description
            #
            # Physical serial ports can't know what's connected to them, but they are
            # also more likely to have stable device path so there is less need for filter.
            if port_info.description:
                text = port_info.description
                text = text.replace(port_info.device_path, '').strip()
                text = text.strip('-: ')
                if text:
                    self.port_filter_name = re.escape(text)

    def port_by_path(self, device_path):
        for port in self.ports:
            if port.device_path == device_path:
                return port
        return None

    def get_matching_port(self):
        for port in self.ports:
            if self.port_matches(port):
                return port
        return None

    def choose_filtered_port(self):
        if not self.has_port_filter():
            return self.port

        self.refresh()
        port_info = self.port_by_path(self.port)
        if port_info and self.port_matches(port_info):
            return port_info.device_path # prefer last used port when suitable

        port_info = self.get_matching_port()
        if port_info:
            return port_info.device_path

        return None


class SerialConfig(SerialConfigBase):
    def _default_ports(self):
        result = []
        for port in comports():
            info = SerialPortInfo()
            info.device_path = port.device
            info.description = str(port)
            info.usb_pid = port.pid if port.pid else 0
            info.usb_vid = port.vid if port.vid else 0
            result.append(info)
        return result


class SerialTransport(RawFdTransport):
    #: Default config
    config = Instance(SerialConfig, ()).tag(config=True)

    #: Connection port
    connection = Instance(SerialPort)

    #: Whether a serial connection spools depends on the device (configuration)
    always_spools = set_default(False)

    def connect(self):
        config = self.config
        try:
            #: Save a reference
            self.protocol.transport = self

            #: Make the wrapper
            self._protocol = RawFdProtocol(self, self.protocol)

            port = self.config.choose_filtered_port()
            if not port:
                raise Exception("{} | Could not find suitable port".format(config.port))
            self.config.port = port  # might be updated if there is a filter
            self.device_path = config.port

            self.connection = SerialPort(
                self._protocol,
                port,
                reactor,
                baudrate=config.baudrate,
                bytesize=config.bytesize,
                parity=config.parity,
                stopbits=config.stopbits,
                xonxoff=config.xonxoff,
                rtscts=config.rtscts
            )

            # Twisted is missing this
            if config.dsrdtr:
                try:
                    self.connection._serial.dsrdtr = True
                except AttributeError as e:
                    log.warning("{} | dsrdtr is not supported {}".format(
                        config.port, e))

            log.debug("{} | opened".format(config.port))
        except Exception as e:
            #: Make sure to log any issues as these tracebacks can get
            #: squashed by twisted
            log.error("{} | {}".format(config.port, traceback.format_exc()))
            raise


class SerialPlugin(Plugin):
    """ Plugin for handling serial port communication

    """

    # -------------------------------------------------------------------------
    # SerialPlugin API
    # -------------------------------------------------------------------------
