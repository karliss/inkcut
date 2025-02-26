# -*- coding: utf-8 -*-
"""
Created on Jul 25, 2015

@author: jrm
"""
from atom.api import Instance, Float, Bool, Int
from inkcut.device.plugin import DeviceProtocol, Model
from inkcut.core.utils import log, to_speed_unit


class HPGLConfig(Model):
    #: Pad option
    pad = Bool().tag(config=True)
    ignore_protocol_scale = Bool(False).tag(config=True)


class HPGLProtocol(DeviceProtocol):
    DEFAULT_SCALE = (1016 / 90.0)

    #: Pad option
    config = Instance(HPGLConfig, ()).tag(config=True)

    def write(self, data):
        if self.config.pad:
            data += "\n"
        super().write(data)

    def connection_made(self):
        #: Initialize in absoulte mode
        self.write("IN;")

    def move(self, x, y, z, absolute=True):
        """ Move the given position. If absolute is true use a PR
        otherwise use PA. Most of the chinese machines don't handle
        negative values so absolute moves only works.
        
        """
        scale = self.protocol_scale
        x, y = int(x * scale), int(y * scale)
        if absolute:
            self.write("%s%i,%i;" % ('PD' if z else 'PU', x, y))
        else:
            self.write('PR%i,%i;' % (x, y))

    def set_force(self, f):
        self.write("FS%i; " % f)

    def set_velocity(self, v):
        # HP DraftPro programmers reference says that speed units are cm/s
        # HP 7585B service manual -> "1 to 6cm/s (0.4 to 24in/s) in 1cm increments"
        # Siemens C1613 PROGRAMMIERHANDBUCH cm/sek
        # Roland DPX-3300 operation manual cm/s
        self.write("VS{}".format(round(to_speed_unit(v, 'cm/s'))))

    def set_pen(self, p):
        self.write("SP%i;" % p)

    def finish(self):
        # Reinitialize
        self.write("IN;")

    @property
    def protocol_scale(self):
        if self.config.ignore_protocol_scale:
            return 1
        return HPGLProtocol.DEFAULT_SCALE
