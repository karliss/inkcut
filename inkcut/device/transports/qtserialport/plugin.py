# -*- coding: utf-8 -*-
"""
Copyright (c) 2020, Laszlo Ducsai

Distributed under the terms of the GPL v3 License.

The full license is in the file LICENSE, distributed with this software.

Created on Oct 26, 2020

@author: ducsi
"""
import sys
import traceback
from atom.atom import set_default
from atom.api import List, Instance, Enum, Bool, Int, Str
from inkcut.core.api import Plugin, Model, log
from inkcut.device.transports.serialport.plugin import SerialConfigBase, SerialPortInfo
from inkcut.device.plugin import DeviceTransport
from qtpy.QtSerialPort import QSerialPort, QSerialPortInfo
import serial

class QtSerialConfig(SerialConfigBase):
    def _default_ports(self):
        result = []
        for port in QSerialPortInfo().availablePorts():
            info = SerialPortInfo()
            info.device_path = port.portName()
            info.description = "{} {}".format(port.portName(), port.description())
            if port.hasProductIdentifier() and port.hasVendorIdentifier():
                info.usb_pid = port.productIdentifier()
                info.usb_vid = port.vendorIdentifier()
            result.append(info)
        return result

    def map_flow_control(self):
        if self.rtscts:
            return QSerialPort.FlowControl.HardwareControl
        elif self.xonxoff:
            return QSerialPort.FlowControl.SoftwareControl
        return QSerialPort.FlowControl.NoFlowControl

    STOP_BIT_MAPPING = {
        serial.STOPBITS_ONE: QSerialPort.StopBits.OneStop,
        serial.STOPBITS_ONE_POINT_FIVE: QSerialPort.StopBits.OneAndHalfStop,
        serial.STOPBITS_TWO: QSerialPort.StopBits.TwoStop,
    }

    def map_stop_bits(self):
        return QtSerialConfig.STOP_BIT_MAPPING[self.stopbits]

    PARITY_BIT_MAPPING = {
        serial.PARITY_NONE: QSerialPort.Parity.NoParity,
        serial.PARITY_EVEN: QSerialPort.Parity.EvenParity,
        serial.PARITY_ODD: QSerialPort.Parity.OddParity,
        serial.PARITY_MARK: QSerialPort.Parity.SpaceParity,
        serial.PARITY_SPACE: QSerialPort.Parity.MarkParity,
    }

    def map_parity(self):
        return QtSerialConfig.PARITY_BIT_MAPPING[self.parity]

    BYTESIZE_MAPPING = {
        5: QSerialPort.DataBits.Data5,
        6: QSerialPort.DataBits.Data6,
        7: QSerialPort.DataBits.Data7,
        8: QSerialPort.DataBits.Data8,
    }

    def map_bytesize(self):
        return QtSerialConfig.BYTESIZE_MAPPING[self.bytesize]

class QtSerialTransport(DeviceTransport):
    __slots__ = ('__weakref__',) # needed to for connection with Qt signals, at least with PyQt6

    #: Default config
    config = Instance(QtSerialConfig, ()).tag(config=True)
    #: Current path
    device_path = Str()
    #: Connection port
    connection = Instance(QSerialPort)

    #: Whether a serial connection spools depends on the device (configuration)
    always_spools = set_default(False)

    def open_serial_port(self, config):
        try:
            port_name = self.config.choose_filtered_port()
            if not port_name:
                raise Exception("{} | Could not find suitable port".format(config.port))
            self.config.port = port_name  # might be updated if there is a filter


            serial_port = QSerialPort()
            serial_port.setPortName(port_name)
            #Setting the AllDirections flag is supported on all platforms. Windows supports only this mode.
            serial_port.setBaudRate(config.baudrate, QSerialPort.Direction.AllDirections)
            serial_port.setParity(config.map_parity())
            serial_port.setStopBits(config.map_stop_bits())
            serial_port.setDataBits(config.map_bytesize())
            serial_port.setFlowControl(config.map_flow_control())
            serial_port.open(QSerialPort.ReadWrite)
            foo = self.on_data_receive_ready
            serial_port.readyRead.connect(self.on_data_receive_ready)
            return serial_port
        except Exception as e:
            log.error("{}".format(traceback.format_exc()))
            return None

    def on_data_receive_ready(self):
        if not self.connection:
            return
        while self.connection.bytesAvailable() > 0:
            data = self.connection.read(self.connection.bytesAvailable())
            self.protocol.data_received(data)
            self.last_read = data

    def connect(self):
        config = self.config
        self.device_path = config.port
        try:
            #: Save a reference
            self.protocol.transport = self
            
            self.connection = self.open_serial_port(config)
            self.connected = True
            log.debug("{} | opened".format(config.port))
            self.protocol.connection_made()
            
        except Exception as e:
            #: Make sure to log any issues
            log.error("{} | {}".format(config.port, traceback.format_exc()))
            raise
            
    def write(self, data):
        if not self.connection:
            raise IOError("{} is not opened".format(self.device_path))
        log.debug("-> {} | {}".format(self.device_path, data))
        if hasattr(data, 'encode'):
            data = data.encode()
        self.last_write = data
        self.connection.write(data)
        
    def disconnect(self):
        if self.connection:
            log.debug("-- {} | closed by request".format(self.device_path))
            self.connected=False
            self.connection.close()
            self.connection = None

    def __repr__(self):
        return self.device_path


class QtSerialPlugin(Plugin):
    """ Plugin for handling serial port communication

    """
    # -------------------------------------------------------------------------
    # SerialPlugin API
    # -------------------------------------------------------------------------