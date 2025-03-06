# -*- coding: utf-8 -*-
"""
Copyright (c) 2019, Jairus Martin.

Distributed under the terms of the GPL v3 License.

The full license is in the file LICENSE, distributed with this software.

Created on June 7, 2019

@author: jrm
"""
import re
import sys
import traceback
import subprocess
from glob import glob
from atom.api import Atom, List, Str, Instance, Value
from inkcut.core.api import Plugin, log
from inkcut.device.plugin import DeviceTransport
from twisted.internet import abstract, fdesc
import twisted.internet

from inkcut.device.transports.raw.plugin import RawFdProtocol, RawFdConfig


class ParallelPortDescriptor(Atom):
    name = Str()
    device = Str()

    def __str__(self):
        return "{} ({})".format(self.name, self.device)


def find_dev_name(dev):
    """Use udevadm to lookup info on a device

    Parameters
    ----------
    dev: String
        The device path to lookup, eg /dev/usb/lp1

    Returns
    -------
    name: String
        The device name

    """
    try:
        cmd = "udevadm info -a %s" % dev
        manufacturer = ""
        product = ""

        output = subprocess.check_output(cmd.split())
        if sys.version_info.major > 2:
            output = output.decode()
        for line in output.split("\n"):
            log.debug(line)
            m = re.search(r'ATTRS{(.+)}=="(.+)"', line)
            if m:
                k, v = m.groups()
                if k == "manufacturer":
                    manufacturer = v.strip()
                elif k == "product":
                    product = v.strip()
            if manufacturer and product:
                return "{} {}".format(manufacturer, product)
        log.warning("Could not lookup device info for %s" % dev)
    except Exception as e:
        tb = traceback.format_exc()
        log.warning("Could not lookup device info for %s  %s" % (dev, tb))
    return "usb%s" % dev.split("/")[-1]


def find_ports():
    """Lookup ports from known locations on the system

    Returns
    -------
    ports: List[ParallelPortDescriptor]
        The ports found on the system

    """
    ports = []
    if "win32" in sys.platform:
        pass  # TODO
    elif "darwin" in sys.platform:
        pass  # TODO
    else:
        for p in glob("/dev/lp*"):
            # TODO: Get friendly device name
            name = p.split("/")[-1]
            ports.append(ParallelPortDescriptor(device=p, name=name))

        for p in glob("/dev/parport*"):
            # TODO: Get friendly device name
            name = p.split("/")[-1]
            ports.append(ParallelPortDescriptor(device=p, name=name))

        for p in glob("/dev/usb/lp*"):
            name = find_dev_name(p)
            ports.append(ParallelPortDescriptor(device=p, name=name))

    return ports


class ParallelConfig(RawFdConfig):
    #: Available serial ports
    ports = List(ParallelPortDescriptor)

    # -------------------------------------------------------------------------
    # Defaults
    # -------------------------------------------------------------------------
    def _default_ports(self):
        return find_ports()

    def _default_device_path(self):
        if self.ports:
            return self.ports[0].device
        return ""

    def refresh(self):
        self.ports = self._default_ports()


class ParallelTwistedTransport(abstract.FileDescriptor):
    connected = 1

    def __init__(
        self,
        port_name: str,
        protocol: RawFdProtocol,
        reactor=None,
    ):
        abstract.FileDescriptor.__init__(self, reactor)
        self.fd = open(port_name, "r+b")
        fdesc.setNonBlocking(self.fileno())
        self.protocol = protocol
        self.written_something = False
        self.protocol.makeConnection(self)
        self.startReading()

    def fileno(self):
        return self.fd.fileno()

    def writeSomeData(self, data):
        res = fdesc.writeToFD(self.fileno(), data)
        self.written_something = self.written_something or res > 0
        return res

    def doRead(self):
        return fdesc.readFromFD(self.fileno(), self.protocol.dataReceived)

    def doWrite(self):
        self.written_something = False
        return abstract.FileDescriptor.doWrite(self)

    def stopWriting(self):
        abstract.FileDescriptor.stopWriting(self)

    def connectionLost(self, reason):
        if (
            self.written_something
            and "linux" in sys.platform
            and isinstance(reason.value, twisted.internet.error.ConnectionDone)
        ):

            # Queue up one more iteration in select loop to wait until write is really done.
            # Linux usblp driver has a documented quirk where closing it in nonblocking mode can cause dropping
            # pending data.
            # https://github.com/torvalds/linux/blob/df87d843c6eb4dad31b7bf63614549dd3521fe71/drivers/usb/class/usblp.c#L893C1-L898C1
            # https://github.com/karliss/inkcut/issues/56
            self.startWriting()
            return

        abstract.FileDescriptor.connectionLost(self, reason)
        self.fd.close()
        self.protocol.connectionLost(reason)
        log.debug("Closed {}".format(self.fd.name))


class ParallelTransport(DeviceTransport):
    """This is just a wrapper for the RawFdTransport"""

    #: Default config
    config = Instance(ParallelConfig, ()).tag(config=True)

    #: Current path
    device_path = Str()
    #: Wrapper which forwards twisted protocol to inkcut
    _wrapper_protocol = Instance(RawFdProtocol)

    #: A raw device connection
    connection = Instance(ParallelTwistedTransport)

    def connect(self):
        config = self.config
        device_path = self.device_path = config.device_path
        try:
            log.debug("-- {} | opened".format(device_path))
            self._wrapper_protocol = RawFdProtocol(self, self.protocol)
            self.connection = ParallelTwistedTransport(
                device_path, self._wrapper_protocol
            )
        except Exception as e:
            #: Make sure to log any issues as these tracebacks can get
            #: squashed by twisted
            log.error(
                "Parallel port open failed {} | {}".format(
                    device_path, traceback.format_exc()
                )
            )
            raise

    def write(self, data):
        if not self.connection:
            raise IOError("{} is not opened".format(self.device_path))
        log.debug("-> {} | {}".format(self.device_path, data))
        if hasattr(data, "encode"):
            # TODO: cleanup str/byte handling transport should always receive bytes not strings
            data = data.encode()
        self.last_write = data
        self.connection.write(data)

    def disconnect(self):
        if self.connection:
            log.debug("-- {} | closed by request".format(self.device_path))
            self.connection.loseConnection()
            self.connection = None

    def __repr__(self):
        return self.device_path

    @property
    def always_disconnect_after_job(self) -> bool:
        return False

    @property
    def auto_disconnect_after_job(self) -> bool:
        return self.config.close_after_job


class ParallelPlugin(Plugin):
    """Plugin for handling parallel port communication"""
