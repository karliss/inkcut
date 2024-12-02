"""
Copyright (c) 2017, Jairus Martin.

Distributed under the terms of the GPL v3 License.

The full license is in the file LICENSE, distributed with this software.

Created on Jul 12, 2015

@author: jrm
"""
from typing import Optional

import pyqtgraph as pg
from atom.api import List, Instance, Enum, Bool, Range, Int, observe
from enaml.application import timed_call
from enaml.qt import QtCore, QtGui
from enaml.qt.QtCore import QPointF
from enaml.qt.QtGui import QPainterPath, QTransform

import inkcut.core.utils
from inkcut.core.api import Plugin, Model, unit_conversions, log
from .plot_view import PainterPathPlotItem
from ..core import utils
from ..device.plugin import DeviceConfig, Device, DevicePlugin
from ..job.plugin import JobPlugin

QPen = QtGui.QPen


class PreviewModel(Model):
    #: List of plot items to display
    plot = List()

    #: Internal paths for drawing
    paths = List(QtGui.QPainterPath)

    #: Colors
    pen_media = Instance(QPen)
    pen_media_padding = Instance(QPen)
    pen_up = Instance(QPen)
    pen_offset = Instance(QPen)
    pen_down = Instance(QPen)
    pen_tool_path = Instance(QPen)
    pen_device = Instance(QPen)

    need_redraw = Int(default=0)

    def _default_pen_media(self):
        return pg.mkPen((128, 128, 128))

    def _default_pen_media_padding(self):
        return pg.mkPen((128, 128, 128), style=QtCore.Qt.DashLine)

    def _default_pen_device(self):
        return pg.mkPen((235, 194, 194), style=QtCore.Qt.DashLine)

    def _default_pen_up(self):
        return pg.mkPen(hsv=(0.53, 1, 0.5, 0.5))

    def _default_pen_tool_path(self):
        return pg.mkPen(hsv=(0.064, 0.905, 0.96, 1), style=QtCore.Qt.DashLine)

    def _default_pen_down(self):
        return pg.mkPen((128, 128, 128))

    def init(self, view_items, clear_main_paths=True):
        default_items = []
        if clear_main_paths or not self.paths:
            self.paths = [QtGui.QPainterPath(), QtGui.QPainterPath()]

        default_items.append(PainterPathPlotItem(
            self.paths[0], pen=self.pen_down))
        default_items.append(PainterPathPlotItem(
            self.paths[1], pen=self.pen_up))
        self.plot = default_items + view_items

    def queue_redraw(self, type):
        if self.need_redraw == 0:
            timed_call(20, self.redraw)
        self.need_redraw |= (1 << type)
    
    def redraw(self):
        layers_to_update = self.need_redraw
        self.need_redraw = 0
        if layers_to_update & (1 << 0):
            self.plot[0].updateData(self.paths[0])
        if layers_to_update & (1 << 1):
            self.plot[1].updateData(self.paths[1])

    def update(self, position):
        """ Watch the position of the device as it changes. """
        if not self.paths:
            return
        x, y, z = position
        if z:
            self.paths[0].lineTo(x, y)
            self.paths[1].moveTo(x, y)
            self.queue_redraw(0)
        else:
            self.paths[0].moveTo(x, y)
            self.paths[1].lineTo(x, y)
            self.queue_redraw(1)


class PreviewPlugin(Plugin):

    #: Set's the plot that is drawn in the preview
    preview = Instance(PreviewModel, ())

    #: Plot for showing live status
    live_preview = Instance(PreviewModel, ())

    #: Transform applied to all view items
    transform = Instance(QtGui.QTransform)

    show_grid_x = Bool().tag(config=True)
    show_grid_y = Bool().tag(config=True)
    grid_alpha = Range(value=30, low=1, high=100).tag(config=True)
    show_moves = Bool(default=True).tag(config=True)
    show_drawing = Bool(default=True).tag(config=True)
    show_processed_path = Bool().tag(config=True)

    job_plugin: Optional[JobPlugin]
    device_plugin: DevicePlugin
    device = Instance(Device, optional=True)

    def start(self):
        """ Start listening for command updates """
        super().start()
        self._bind_extra_observers()
        self.device = self.device_plugin.device
        if self.device:
            self._refresh_preview(None)

    def stop(self):
        self._unbind_extra_observers()
        super().stop()

    def _bind_extra_observers(self):
        workbench = self.workbench
        job_plugin = self.job_plugin = workbench.get_plugin('inkcut.job')
        job_plugin.observe('content_changed', self._refresh_preview)
        device_plugin = self.device_plugin =  workbench.get_plugin('inkcut.device')
        device_plugin.observe('device', self._update_device)

    def _unbind_extra_observers(self):
        self.job_plugin.unobserve('content_changed', self._refresh_preview)
        self.device_plugin.unobserve('device', self._update_device)

    def _default_transform(self):
        """ Qt displays top to bottom so this can be used to flip it.

        """
        return QtGui.QTransform.fromScale(1, -1)

    def _default_job_plugin(self):
        self.job_plugin = self.workbench.get_plugin('inkcut.job')

    def _update_device(self, change):
        log.debug('update device')
        self.device = change['value']

    def set_preview(self, *items):
        """ Sets the items that will be displayed in the plot

        Parameters
        ----------
        items: list of kwargs
            A list of kwargs to to pass to each plot item

        """
        view_items = [
            PainterPathPlotItem(kwargs.pop('path'), **kwargs)
            for kwargs in items
        ]
        self.preview.plot = view_items

    @observe('device')
    def _reset_live_preview(self, change):
        self.reset_live_preview(self.device, self.device.job, clear_paths=True)

    @observe('device.origin', 'device.job', 'device.alignment_corner', 'device.paper_corner', 'device.area')
    def _reset_live_preview2(self, change):
        self.reset_live_preview(self.device, self.device.job, clear_paths=False)

    @observe('device.position')
    def _update_live_preview(self, change):
        """ Watch the position of the device as it changes. """
        if change['type'] == 'update' and self.device.job:
            x, y, z = change['value']
            origin = self.device.config.inverse_transform.map(QPointF(x, y))
            x, y = origin.x(), origin.y()
            self.live_preview.update((x, y, z))

    def set_live_preview(self, *items, clear_paths=True):
        """ Set the items that will be displayed in the live plot preview.
        After set, use live_preview.update(position) to update it.

        Parameters
        ----------
        items: list of kwargs
            A list of kwargs to to pass to each plot item


        """
        view_items = [
            PainterPathPlotItem(kwargs.pop('path'), **kwargs)
            for kwargs in items
        ]
        self.live_preview.init(view_items, clear_main_paths=clear_paths)

    def reset_live_preview(self, device, job, clear_paths=True):
        """ Redraw the live preview on the screen

                """
        view_items = []

        if job:
            job.set_direction(device.config.expansion_direction)

        #: Transform used by the view
        plot = self.live_preview

        #: Draw the device
        if device:
            view_items.append(
                dict(path=utils.rect_to_path(device.area_rect),
                     pen=plot.pen_device,
                     skip_autorange=True)
            )

        if job and job.material:
            # Also observe any change to job.media and job.device
            page_rect = job.material.get_rect(job.quadrant_direction)
            padded_page = job.material.get_content_rect(job.quadrant_direction)
            t = device.config.get_paper_to_work_transform(job.material)
            origin = device.config.inverse_transform.map(QPointF(device.origin[0], device.origin[1]))
            t.translate(origin.x(), origin.y())
            view_items.extend([
                dict(path=utils.rect_to_path(t.mapRect(page_rect)),
                     pen=plot.pen_media,
                     skip_autorange=True),
                dict(path=utils.rect_to_path(t.mapRect(padded_page)),
                     pen=plot.pen_media_padding, skip_autorange=True)
            ])

        #: Update the plot
        self.set_live_preview(*view_items, clear_paths=clear_paths)

    @observe('show_moves', 'show_drawing', 'show_processed_path')
    def _refresh_preview(self, change):
        """Redraw the main preview in central area of program"""
        log.info(change)
        view_items = []

        if not self.job_plugin:
            return

        #: Transform used by the view
        job = self.job_plugin.job
        plot = self.preview
        t = self.transform

        #: Draw the device
        device_plugin = self.workbench.get_plugin("inkcut.device")
        device = device_plugin.device
        device_config: DeviceConfig = device.config
        job.set_direction(device_config.expansion_direction)

        #: Apply the final output transforms from the device
        page_transform = QTransform()
        if job.material and device and device.config.area:
            page_transform = device_config.get_paper_to_work_transform(job.material)

        def transform(p):
            return page_transform.map(p)

        if device and device.config.area:
            view_items.append(
                dict(
                    path=utils.rect_to_path(device.area_rect),
                    pen=plot.pen_device,
                    skip_autorange=True,
                )  # (False, [area.size[0], 0]))
            )

        if job.material:
            # Also observe any change to job.media and job.device

            page_rect = job.material.get_rect(job.quadrant_direction)
            padded_page = job.material.get_content_rect(job.quadrant_direction)
            view_items.extend(
                [
                    dict(
                        path=transform(utils.rect_to_path(page_rect)),
                        pen=plot.pen_media,
                        skip_autorange=([0, job.size[0]], [0, job.size[1]]),
                    ),
                    dict(
                        path=transform(utils.rect_to_path(padded_page)),
                        pen=plot.pen_media_padding,
                        skip_autorange=True,
                    ),
                ]
            )

        #: The model is only set when a document is open and has no errors
        if job.model:
            model = job.model

            if self.show_drawing:
                view_items.append(dict(path=transform(job.model), pen=plot.pen_down))

            if self.show_processed_path:
                model = job.create_transform_filtered(device)
                view_items.append(dict(path=transform(model), pen=plot.pen_tool_path))

            if self.show_moves:
                view_items.append(dict(path=transform(inkcut.core.utils.make_move_path(model)), pen=plot.pen_up))


        self.set_preview(*view_items)