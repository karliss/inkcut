# -*- coding: utf-8 -*-
"""
Created on Jul 25, 2015

Thanks to Lex Wernars

@author: jrm
@author: lwernars
"""

from inkcut.device.plugin import DeviceProtocol
from atom.api import Instance, Float, Bool, Int, Enum
from inkcut.device.plugin import DeviceProtocol, Model
from inkcut.core.utils import to_unit


class GPGLConfig(Model):
    SCALE_IGNORE = 0
    SCALE_1MM = 1  # 0.1mm
    SCALE_025MM = 2  # 0.025mm

    unit_mode = Enum(SCALE_025MM, SCALE_1MM, SCALE_IGNORE).tag(config=True)


class GPGLProtocol(DeviceProtocol):
    config = Instance(GPGLConfig, ()).tag(config=True)

    def connection_made(self):
        self.write("H")

    def move(self, x, y, z, absolute=True):
        scale = self.protocol_scale
        x *= scale
        y *= scale
        x = round(x)
        y = round(y)
        if absolute:
            self.write("%s%i,%i" % ('D' if z else 'M', x, y))
        else:
            self.write("%s%i,%i" % ('E' if z else 'O', x, y))

    def set_velocity(self, v):
        # MP4000 series command set reference manual -> 10mm/s = cm/s
        # note that speed can be set in two different modes 1-10  uses an abstract scale from min to max speed
        # 100...(max_speed+100) specifies spped offset by 100 in cm/s
        speed = max(1, round(to_unit(v, "cm")))
        self.write('!{:i}'.format(speed + 100))

    def set_force(self, f):
        self.write("FX%i,1" % f)

    def set_pen(self, p):
        pass

    @property
    def protocol_scale(self):
        if self.config.unit_mode == GPGLConfig.SCALE_025MM:
            return 40 * 25.4 / 90.0
        elif self.config.unit_mode == GPGLConfig.SCALE_1MM:
            return 10 * 25.4 / 90.0
        else:
            return 1
