"""
Copyright (c) 2024, Karlis Senko

Distributed under the terms of the GPL v3 License.

The full license is in the file LICENSE, distributed with this software.

Created on Dec 9, 2024

@author: karliss
"""
import pytest
from inkcut.device.transports.serialport.plugin import SerialConfigBase, SerialPortInfo


def test_serial_filter():
    info = SerialPortInfo(device_path='port1')
    config = SerialConfigBase()

    assert not config.has_port_filter()
    assert config.port_matches(info)

    config = SerialConfigBase(port_filter_name='ort')

    assert config.has_port_filter()
    assert not config.port_matches(info)

    assert config.port_matches(SerialPortInfo(description='Port1', usb_vid=1, usb_pid=1))
    assert not config.port_matches(SerialPortInfo(description='P_rt1', usb_vid=1, usb_pid=1))

    config = SerialConfigBase(port_filter_vid=5)
    assert config.port_matches(SerialPortInfo(description='Port1', usb_vid=5, usb_pid=1))
    assert config.port_matches(SerialPortInfo(usb_vid=5, usb_pid=1))
    assert not config.port_matches(SerialPortInfo(description='Port1', usb_vid=1, usb_pid=1))

    config = SerialConfigBase(port_filter_pid=10)
    assert config.port_matches(SerialPortInfo(description='Port1', usb_vid=5, usb_pid=10))
    assert config.port_matches(SerialPortInfo(usb_vid=4, usb_pid=10))
    assert not config.port_matches(SerialPortInfo(description='Port1', usb_vid=2, usb_pid=2))

    config = SerialConfigBase(port_filter_name='Port1', port_filter_vid=0x1234, port_filter_pid=0x45ac)
    assert config.port_matches(SerialPortInfo(description='Port1', usb_vid=0x1234, usb_pid=0x45ac))
    assert not config.port_matches(SerialPortInfo(description='Port1', usb_vid=0x1234, usb_pid=0x45ad))
    assert not config.port_matches(SerialPortInfo(description='Port1', usb_vid=0x1235, usb_pid=0x45ac))
    assert not config.port_matches(SerialPortInfo(description='Port2', usb_vid=0x1234, usb_pid=0x45ac))

    config = SerialConfigBase(port_filter_name='P.*1')
    assert config.port_matches(SerialPortInfo(description='Port1', usb_vid=1, usb_pid=1))
    assert config.port_matches(SerialPortInfo(description='Pooooooort1', usb_vid=1, usb_pid=1))
    assert not config.port_matches(SerialPortInfo(description='P..', usb_vid=1, usb_pid=1))

    config = SerialConfigBase(port_filter_name='^Port1$')
    assert config.port_matches(SerialPortInfo(description='Port1', usb_vid=1, usb_pid=1))
    assert not config.port_matches(SerialPortInfo(description='Port12', usb_vid=1, usb_pid=1))


def test_make_filter():
    info = SerialPortInfo(device_path='port1', description='Port1 some plotter', usb_vid=123, usb_pid=321)
    config = SerialConfigBase()

    config.make_filter(info)
    assert config.has_port_filter()
    assert config.port_matches(info)

    info_2 = SerialPortInfo(device_path='port1', description='Port1 other plotter', usb_vid=123, usb_pid=321)
    assert not config.port_matches(info_2)

    info_2 = SerialPortInfo(device_path='port1', description='Port1 some plotter', usb_vid=124, usb_pid=321)
    assert not config.port_matches(info_2)

    info_2 = SerialPortInfo(device_path='port1', description='Port1 some plotter', usb_vid=123, usb_pid=421)
    assert not config.port_matches(info_2)

    config.clear_filter()
    assert not config.has_port_filter()

    info = SerialPortInfo(device_path='port1', description=r"a+.*?(){},{^$|\\", usb_vid=123, usb_pid=321)
    config = SerialConfigBase()
    config.make_filter(info)
    assert config.port_matches(info)
    assert not config.port_matches(SerialPortInfo(description='a', usb_vid=123, usb_pid=321))

    info = SerialPortInfo(device_path='/dev/someport1', description=r" /dev/someport1: description",
                          usb_vid=123, usb_pid=321)
    config = SerialConfigBase()
    config.make_filter(info)
    assert config.port_filter_name == "description"

    info = SerialPortInfo(device_path='COM3', description=r" (COM3) description (COM3) ",
                          usb_vid=123, usb_pid=321)
    config = SerialConfigBase()
    config.make_filter(info)
    assert config.port_matches(info)
    assert not config.port_matches(SerialPortInfo(device_path='COM3', description=r"zescriptionz",
                          usb_vid=123, usb_pid=321))
