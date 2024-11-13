# -*- coding: utf-8 -*-
"""
Created on Jul 25, 2015

Thanks to Lex Wernars

@author: jrm
@author: lwernars
"""
from atom.api import Enum, Instance, Float

from inkcut.core.utils import to_unit
from inkcut.device.plugin import DeviceProtocol, Model


class DMPLConfig(Model):
    #: Version number
    mode = Enum(1, 2, 3, 4).tag(config=True)
    SCALE_IGNORE = 0
    SCALE_001_IN = 1
    SCALE_005_IN = 2
    SCALE_1_MM = 3
    SCALE_025_MM = 4

    #TODO: LOOK into EC0.
    SCALE_MAPPING = {
        SCALE_IGNORE: "",
        SCALE_001_IN: "EC1",
        SCALE_005_IN: "EC5",
        SCALE_1_MM: "ECM",
        SCALE_025_MM: "ECN",
    }

    unit_mode = Enum(SCALE_025_MM, SCALE_1_MM, SCALE_005_IN, SCALE_001_IN, SCALE_IGNORE).tag(config=True)


class DMPLProtocol(DeviceProtocol):

    #: Different modes
    config = Instance(DMPLConfig, ()).tag(config=True)

    def get_scale_cmd(self):
        return DMPLConfig.SCALE_MAPPING.get(self.config.unit_mode, "")

    def connection_made(self):
        v = self.config.mode

        scale_cmd = self.get_scale_cmd()
        if v == 1:
            self.write(";:HA{}".format(scale_cmd))
        elif v == 2:
            self.write(" ;:{} A L0 ".format(scale_cmd))
        elif v in [3, 4]:
            self.write(" ;:H A L0 ")

    def move(self, x, y, z, absolute=True):
        scale = self.protocol_scale()
        x, y = int(x*scale), int(y*scale)
        v = self.config.mode
        self.write(" {z}{x},{y} ".format(x=x, y=y, z=z and "D" or "U"))

    @property
    def protocol_scale(self):
        if self.config.unit_mode == DMPLProtocol.SCALE_001_IN:
            return 1000 / 90.0
        elif self.config.unit_mode == DMPLProtocol.SCALE_005_IN:
            return 200 / 90.0
        if self.config.unit_mode == DMPLProtocol.SCALE_1_MM:
            return 10 * 25.4 / 90.0
        elif self.config.unit_mode == DMPLProtocol.SCALE_025MM:
            return 40 * 25.4 / 90.0
        else:
            return 1

    def set_pen(self, p):
        self.write("P{p} ".format(p=p))

    def set_velocity(self, v):
        if self.config.scale_mode == DMPLConfig.SCALE_001_IN or self.config.scale_mode == DMPLConfig.SCALE_005_IN:
            v = to_unit(v, "in")
        else:
            v = to_unit(v, "cm")
        self.write("V{v:.0f} ".format(v=v))

    def set_force(self, f):
        self.write("BP{f} ".format(f=f))

    def connection_lost(self):
        pass
