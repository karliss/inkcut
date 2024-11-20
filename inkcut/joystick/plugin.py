# -*- coding: utf-8 -*-
"""
Copyright (c) 2017, Jairus Martin.

Distributed under the terms of the GPL v3 License.

The full license is in the file LICENSE, distributed with this software.

Created on Jul 19, 2015

@author: jrm
"""
import functools
from atom.api import Instance, Float, observe
from enaml.qt import QtCore, QtGui
from twisted.internet import defer

from inkcut.core.api import Plugin
from inkcut.device.plugin import Device


def with_connection(f):

    @functools.wraps(f)
    @defer.inlineCallbacks
    def wrapped(self, *args, **kwargs):
        device = self.device
        connected = device.connection.connected
        if not connected:
            yield defer.maybeDeferred(self.device.connect)

        #: Call original method
        f(self, *args, **kwargs)

        #if not connected:
        #    yield defer.maybeDeferred(self.device.disconnect)

    return wrapped


class JoystickPlugin(Plugin):
    #: Reference to the inkcut.device plugin's device
    device = Instance(Device)

    #: Rate to move
    rate = Float(1).tag(config=True)
    path = Instance(QtGui.QPainterPath)

    #: Reference to the device plugin
    plugin = Instance(Plugin)

    def stop(self):
        """ Delete this plugins references """
        if self.device:
            self.device.close()
        del self.device
        del self.plugin

    def _default_plugin(self):
        return self.workbench.get_plugin('inkcut.device')

    def _default_device(self):
        return self.plugin.device

    @observe('plugin.device')
    def _refresh_device(self, change):
        """ Whenever the device updates on the device plugin, update
        the local reference.
        """
        if self.device != change['value']:
            self.device = change['value']
            return

    def set_origin(self):
        """ Update the origin and clear the position """
        self.device.origin = self.device.position
        #self.device.position = [0, 0, 0]

    @defer.inlineCallbacks
    def reconnect(self):
        yield self.device.connection.disconnect()
        yield self.device.connection.connect()

    @with_connection
    def move_to_origin(self, system=False):
        if system:
            x, y = 0, 0
        else:
            origin = self.device.origin
            pos = self.device.config.inverse_transform.map_point(QtCore.QPointF(origin.x(), origin.y()))
            x, y = pos.x(), pos.y()
        self.device.move([x, y, 0], absolute=True)

    @with_connection
    def move_up(self):
        self.device.move([0, -self.rate, 0], absolute=False)

    @with_connection
    def move_down(self):
        self.device.move([0, self.rate, 0], absolute=False)

    @with_connection
    def move_left(self):
        self.device.move([-self.rate, 0, 0], absolute=False)

    @with_connection
    def move_right(self):
        self.device.move([self.rate, 0, 0], absolute=False)

    @with_connection
    def move_head_up(self):
        self.device.move([0, 0, 0], absolute=False)

    @with_connection
    def move_head_down(self):
        self.device.move([0, 0, 1], absolute=False)
