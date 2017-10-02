#####################################################################
#                                                                   #
# /main.pyw                                                         #
#                                                                   #
# Copyright 2014, Monash University                                 #
#                                                                   #
# This file is part of the program runviewer, in the labscript      #
# suite (see http://labscriptsuite.org), and is licensed under the  #
# Simplified BSD License. See the license.txt file in the root of   #
# the project for the full license.                                 #
#                                                                   #
#####################################################################

import os
import sys
import time
import threading
import logging
import ctypes
import socket
from Queue import Queue
import ast
import pprint

import signal
# Quit on ctrl-c
signal.signal(signal.SIGINT, signal.SIG_DFL)

import labscript_utils.excepthook

# Set working directory to runviewer folder, resolving symlinks
runviewer_dir = os.path.dirname(os.path.realpath(__file__))
os.chdir(runviewer_dir)

try:
    from labscript_utils import check_version
except ImportError:
    raise ImportError('Require labscript_utils > 2.1.0')

check_version('labscript_utils', '2.0', '3')
check_version('qtutils', '2.0.0', '3.0.0')
check_version('zprocess', '1.1.2', '3')

from labscript_utils.setup_logging import setup_logging
logger = setup_logging('runviewer')
labscript_utils.excepthook.set_logger(logger)

from zprocess import zmq_get, ZMQServer
import zprocess.locking
import labscript_utils.h5_lock
import h5py
zprocess.locking.set_client_process_name('runviewer')

# This must be bumped until after the h5_lock import
# This is because the check imports pyqtgraph, which imports h5py
# h5py must be imported after h5_lock, thus we do the check here
check_version('pyqtgraph', '0.9.10', '1')

from qtutils.qt.QtCore import *
from qtutils.qt.QtGui import *
from qtutils.qt.QtWidgets import *
from qtutils.qt.QtCore import pyqtSignal as Signal

import numpy

# must be imported after PySide/PyQt4
import pyqtgraph as pg
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')

from qtutils import *
import qtutils.icons
from blacs.connections import ConnectionTable
import labscript_devices

from labscript_utils.labconfig import LabConfig, config_prefix

from resample import resample as _resample


def set_win_appusermodel(window_id):
    from labscript_utils.winshell import set_appusermodel, appids, app_descriptions
    icon_path = os.path.abspath('runviewer.ico')
    executable = sys.executable.lower()
    if not executable.endswith('w.exe'):
        executable = executable.replace('.exe', 'w.exe')
    relaunch_command = executable + ' ' + os.path.abspath(__file__.replace('.pyc', '.py'))
    relaunch_display_name = app_descriptions['runviewer']
    set_appusermodel(window_id, appids['runviewer'], icon_path, relaunch_command, relaunch_display_name)


SHOT_MODEL__COLOUR_INDEX = 0
SHOT_MODEL__SHUTTER_INDEX = 1
SHOT_MODEL__CHECKBOX_INDEX = 2
SHOT_MODEL__PATH_INDEX = 1
CHANNEL_MODEL__CHECKBOX_INDEX = 0
CHANNEL_MODEL__CHANNEL_INDEX = 0


def int_to_enum(enum_list, value):
    """stupid hack to work around the fact that PySide screws with the type of a variable when it goes into a model. Enums are converted to ints, which then
     can't be interpreted by QColor correctly (for example)
     unfortunately Qt doesn't provide a python list structure of enums, so you have to build the list yourself.
    """

    for item in enum_list:
        if item == value:
            return item
    return value


class ColourDelegate(QItemDelegate):

    def __init__(self, view, *args, **kwargs):
        QItemDelegate.__init__(self, *args, **kwargs)
        self._view = view
        self._colours = [Qt.black, Qt.red, Qt.green, Qt.blue, Qt.cyan, Qt.magenta, Qt.yellow, Qt.gray, Qt.darkRed, Qt.darkGreen, Qt.darkBlue, Qt.darkCyan, Qt.darkMagenta, Qt.darkYellow, Qt.darkGray, Qt.lightGray]

        self._current_colour_index = 0

    def get_next_colour(self):
        colour = self._colours[self._current_colour_index]
        self._current_colour_index += 1
        if self._current_colour_index >= len(self._colours):
            self._current_colour_index = 0
        return colour

    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        #colours = QColor.colorNames()
        for colour in self._colours:
            pixmap = QPixmap(20, 20)
            pixmap.fill(colour)
            editor.addItem(QIcon(pixmap), '', colour)

        editor.activated.connect(lambda index, editor=editor: self._view.commitData(editor))
        editor.activated.connect(lambda index, editor=editor: self._view.closeEditor(editor, QAbstractItemDelegate.NoHint))
        QTimer.singleShot(10, editor.showPopup)

        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.UserRole)
        for i in range(editor.count()):
            if editor.itemData(i) == value():
                editor.setCurrentIndex(i)
                break

    def setModelData(self, editor, model, index):
        icon = editor.itemIcon(editor.currentIndex())
        colour = editor.itemData(editor.currentIndex())

        # Note, all data being written to the model must be read out of the editor PRIOR to calling model.setData()
        #       This is because a call to model.setData() triggers setEditorData(), which messes up subsequent
        #       calls to the editor to determine the currently selected item/data
        model.setData(index, icon, Qt.DecorationRole)
        model.setData(index, lambda clist=self._colours, colour=colour: int_to_enum(clist, colour), Qt.UserRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)


class RunviewerMainWindow(QMainWindow):
    # A signal for when the window manager has created a new window for this widget:
    newWindow = Signal(int)

    def event(self, event):
        result = QMainWindow.event(self, event)
        if event.type() == QEvent.WinIdChange:
            self.newWindow.emit(self.effectiveWinId())
        return result


class RunViewer(object):
    def __init__(self, exp_config):
        self.ui = UiLoader().load(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'main.ui'), RunviewerMainWindow())

        # setup shot treeview model
        self.shot_model = QStandardItemModel()
        self.shot_model.setHorizontalHeaderLabels(['colour', 'shutters', 'path'])
        self.ui.shot_treeview.setModel(self.shot_model)
        self.ui.shot_treeview.resizeColumnToContents(1)
        self.shot_model.itemChanged.connect(self.on_shot_selection_changed)
        self.shot_colour_delegate = ColourDelegate(self.ui.shot_treeview)
        self.ui.shot_treeview.setItemDelegateForColumn(0, self.shot_colour_delegate)

        # setup channel treeview model
        self.channel_model = QStandardItemModel()
        self.channel_model.setHorizontalHeaderLabels(['channel'])
        self.ui.channel_treeview.setModel(self.channel_model)
        self.channel_model.itemChanged.connect(self.update_plots)

        # create a hidden plot widget that all plots can link their x-axis too
        hidden_plot = pg.PlotWidget(name='runviewer - time axis link')

        hidden_plot.setMinimumHeight(40)
        hidden_plot.setMaximumHeight(40)
        hidden_plot.setLabel('bottom', 'Time', units='s')
        hidden_plot.setLabel('left', " ")
        hidden_plot.showAxis('right', True)
        hidden_plot_item = hidden_plot.plot([0, 1], [0, 0])
        self._hidden_plot = (hidden_plot, hidden_plot_item)
        self.ui.plot_layout.addWidget(hidden_plot)

        # add some icons
        self.ui.add_shot.setIcon(QIcon(':/qtutils/fugue/plus'))
        self.ui.delete_shot.setIcon(QIcon(':/qtutils/fugue/minus'))
        self.ui.enable_selected_shots.setIcon(QIcon(':/qtutils/fugue/ui-check-box'))
        self.ui.disable_selected_shots.setIcon(QIcon(':/qtutils/fugue/ui-check-box-uncheck'))
        self.ui.group_channel.setIcon(QIcon(':/qtutils/fugue/layers-group'))
        self.ui.delete_group.setIcon(QIcon(':/qtutils/fugue/layers-ungroup'))
        self.ui.channel_move_to_top.setIcon(QIcon(':/qtutils/fugue/arrow-stop-090'))
        self.ui.channel_move_up.setIcon(QIcon(':/qtutils/fugue/arrow-090'))
        self.ui.channel_move_down.setIcon(QIcon(':/qtutils/fugue/arrow-270'))
        self.ui.channel_move_to_bottom.setIcon(QIcon(':/qtutils/fugue/arrow-stop-270'))
        self.ui.reset_x_axis.setIcon(QIcon(':/qtutils/fugue/clock-history'))
        self.ui.reset_y_axis.setIcon(QIcon(':/qtutils/fugue/magnifier-history'))

        self.ui.actionOpen_Shot.setIcon(QIcon(':/qtutils/fugue/plus'))
        self.ui.actionQuit.setIcon(QIcon(':/qtutils/fugue/cross-button'))
        self.ui.actionLoad_channel_config.setIcon(QIcon(':/qtutils/fugue/folder-open'))
        self.ui.actionSave_channel_config.setIcon(QIcon(':/qtutils/fugue/disk'))

        # disable buttons that are not yet implemented to help avoid confusion!
        self.ui.delete_shot.setEnabled(False)
        self.ui.group_channel.setEnabled(False)
        self.ui.delete_group.setEnabled(False)

        # connect signals
        self.ui.reset_x_axis.clicked.connect(self.on_x_axis_reset)
        self.ui.reset_y_axis.clicked.connect(self.on_y_axes_reset)
        self.ui.channel_move_up.clicked.connect(self._move_up)
        self.ui.channel_move_down.clicked.connect(self._move_down)
        self.ui.channel_move_to_top.clicked.connect(self._move_top)
        self.ui.channel_move_to_bottom.clicked.connect(self._move_bottom)
        self.ui.enable_selected_shots.clicked.connect(self._enable_selected_shots)
        self.ui.disable_selected_shots.clicked.connect(self._disable_selected_shots)
        self.ui.add_shot.clicked.connect(self.on_add_shot)

        self.ui.actionOpen_Shot.triggered.connect(self.on_add_shot)
        self.ui.actionQuit.triggered.connect(self.ui.close)
        self.ui.actionLoad_channel_config.triggered.connect(self.on_load_channel_config)
        self.ui.actionSave_channel_config.triggered.connect(self.on_save_channel_config)

        if os.name == 'nt':
            self.ui.newWindow.connect(set_win_appusermodel)

        self.ui.show()

        # internal variables
        #self._channels_list = {}
        self.plot_widgets = {}
        self.plot_items = {}
        self.shutter_lines = {}

        try:
            self.default_config_path = os.path.join(exp_config.get('DEFAULT', 'app_saved_configs'), 'runviewer')
        except LabConfig.NoOptionError:
            exp_config.set('DEFAULT', 'app_saved_configs', os.path.join('%(labscript_suite)s', 'userlib', 'app_saved_configs', '%(experiment_name)s'))
            self.default_config_path = os.path.join(exp_config.get('DEFAULT', 'app_saved_configs'), 'runviewer')
        if not os.path.exists(self.default_config_path):
            os.makedirs(self.default_config_path)

        self.last_opened_shots_folder = exp_config.get('paths', 'experiment_shot_storage')

        # start resample thread
        self._resample = False
        self._thread = threading.Thread(target=self._resample_thread)
        self._thread.daemon = True
        self._thread.start()

        # start shots_to_process_queue monitoring thread
        self._shots_to_process_thread = threading.Thread(target=self._process_shots)
        self._shots_to_process_thread.daemon = True
        self._shots_to_process_thread.start()

    def _process_shots(self):
        while True:
            filepath = shots_to_process_queue.get()
            inmain_later(self.load_shot, filepath)

    def on_load_channel_config(self):
        config_file = QFileDialog.getOpenFileName(self.ui, "Select file to load", self.default_config_path, "Config files (*.ini)")
        if isinstance(config_file, tuple):
            config_file, _ = config_file
        if config_file:
            runviewer_config = LabConfig(config_file)
            try:
                channels = ast.literal_eval(runviewer_config.get('runviewer_state', 'Channels'))
            except (LabConfig.NoOptionError, LabConfig.NoSectionError):
                channels = {}

            for row, (channel, checked) in enumerate(channels):
                check_items = self.channel_model.findItems(channel)
                if len(check_items) == 0:
                    items = []
                    check_item = QStandardItem(channel)
                    check_item.setEditable(False)
                    check_item.setCheckable(True)
                    items.append(check_item)
                    check_item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                    check_item.setEnabled(False)
                    self.channel_model.insertRow(row, items)
                else:
                    check_item = check_items[0]
                    check_item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                    self.channel_model.takeRow(check_item.row())
                    self.channel_model.insertRow(row, check_item)

    def on_save_channel_config(self):
        save_file = QFileDialog.getSaveFileName(self.ui, 'Select  file to save current channel configuration', self.default_config_path, "config files (*.ini)")
        if type(save_file) is tuple:
            save_file, _ = save_file

        if save_file:
            runviewer_config = LabConfig(save_file)

            channels = []
            for row in range(self.channel_model.rowCount()):
                item = self.channel_model.item(row)
                channels.append((item.text(), item.checkState() == Qt.Checked))

            runviewer_config.set('runviewer_state', 'Channels', pprint.pformat(channels))

    def on_toggle_shutter(self, checked, current_shot):
        for channel in self.shutter_lines:
            for shot in self.shutter_lines[channel]:
                if shot == current_shot:
                    for line in self.shutter_lines[channel][shot][0]:
                        if checked:
                            line.show()
                        else:
                            line.hide()
                    for line in self.shutter_lines[channel][shot][1]:
                        if checked:
                            line.show()
                        else:
                            line.hide()

    def on_add_shot(self):
        selected_files = QFileDialog.getOpenFileNames(self.ui, "Select file to load", self.last_opened_shots_folder, "HDF5 files (*.h5 *.hdf5)")
        popup_warning = False
        if isinstance(selected_files, tuple):
            selected_files, _ = selected_files
        # Convert to standard platform specific path, otherwise Qt likes forward slashes:
        selected_files = [os.path.abspath(str(shot_file)) for shot_file in selected_files]
        if len(selected_files) > 0:
            self.last_opened_shots_folder = os.path.dirname(selected_files[0])

        for file in selected_files:
            try:
                filepath = str(file)
                # Qt has this weird behaviour where if you type in the name of a file that exists
                # but does not have the extension you have limited the dialog to, the OK button is greyed out
                # but you can hit enter and the file will be selected.
                # So we must check the extension of each file here!
                if filepath.endswith('.h5') or filepath.endswith('.hdf5'):
                    self.load_shot(filepath)
                else:
                    popup_warning = True
            except:
                popup_warning = True
                raise
        if popup_warning:
            message = QMessageBox()
            message.setText("Warning: Some shots were not loaded because they were not valid hdf5 files")
            message.setIcon(QMessageBox.Warning)
            message.setWindowTitle("Runviewer")
            message.setStandardButtons(QMessageBox.Ok)
            message.exec_()

    def on_shot_selection_changed(self, item):
        if self.shot_model.indexFromItem(item).column() == SHOT_MODEL__CHECKBOX_INDEX:

            # add or remove a colour for this shot
            checked = item.checkState()
            row = self.shot_model.indexFromItem(item).row()
            colour_item = self.shot_model.item(row, SHOT_MODEL__COLOUR_INDEX)
            check_shutter = self.shot_model.item(row, SHOT_MODEL__SHUTTER_INDEX)

            if checked:
                colour = colour_item.data(Qt.UserRole)
                if colour is not None:
                    colour = colour()
                else:
                    colour = self.shot_colour_delegate.get_next_colour()

                colour_item.setEditable(True)
                pixmap = QPixmap(20, 20)
                pixmap.fill(colour)
                icon = QIcon(pixmap)
                colour_item.setData(lambda clist=self.shot_colour_delegate._colours, colour=colour: int_to_enum(clist, colour), Qt.UserRole)
                colour_item.setData(icon, Qt.DecorationRole)
                if item.data().shutter_times != {}:
                    check_shutter.setEnabled(True)
                else:
                    check_shutter.setEnabled(False)
                    check_shutter.setToolTip("This shot doesn't contain shutter markers")
            else:
                # colour = None
                # icon = None
                colour_item.setEditable(False)
                check_shutter.setEnabled(False)

            # model.setData(index, editor.itemIcon(editor.currentIndex()),
            # model.setData(index, editor.itemData(editor.currentIndex()), Qt.UserRole)

            self.update_channels_treeview()
        elif self.shot_model.indexFromItem(item).column() == SHOT_MODEL__COLOUR_INDEX:
            # update the plot colours

            # get reference to the changed shot
            current_shot = self.shot_model.item(self.shot_model.indexFromItem(item).row(), SHOT_MODEL__CHECKBOX_INDEX).data()

            # find and update the pen of the plot items
            for channel in self.plot_items.keys():
                for shot in self.plot_items[channel]:
                    if shot == current_shot:
                        colour = item.data(Qt.UserRole)
                        self.plot_items[channel][shot].setPen(pg.mkPen(QColor(colour()), width=2))
        elif self.shot_model.indexFromItem(item).column() == SHOT_MODEL__SHUTTER_INDEX:
            current_shot = self.shot_model.item(self.shot_model.indexFromItem(item).row(), SHOT_MODEL__CHECKBOX_INDEX).data()
            self.on_toggle_shutter(item.checkState(), current_shot)

    def load_shot(self, filepath):
        shot = Shot(filepath)

        # add shot to shot list
        # Create Items
        items = []
        colour_item = QStandardItem('')
        colour_item.setEditable(False)
        colour_item.setToolTip('Double-click to change colour')
        items.append(colour_item)

        check_shutter = QStandardItem()
        check_shutter.setCheckable(True)
        check_shutter.setCheckState(Qt.Unchecked)  # options are Qt.Checked OR Qt.Unchecked
        check_shutter.setEnabled(False)
        check_shutter.setToolTip("Toggle shutter markers")
        items.append(check_shutter)

        check_item = QStandardItem(shot.path)
        check_item.setEditable(False)
        check_item.setCheckable(True)
        check_item.setCheckState(Qt.Unchecked)  # options are Qt.Checked OR Qt.Unchecked
        check_item.setData(shot)
        check_item.setToolTip(filepath)
        items.append(check_item)
        # script name
        # path_item = QStandardItem(shot.path)
        # path_item.setEditable(False)
        # items.append(path_item)
        self.shot_model.appendRow(items)

        # only do this if we are checking the shot we are adding
        # self.update_channels_treeview()

    def get_selected_shots_and_colours(self):
        # get the ticked shots
        ticked_shots = {}
        for i in range(self.shot_model.rowCount()):
            item = self.shot_model.item(i, SHOT_MODEL__CHECKBOX_INDEX)
            colour_item = self.shot_model.item(i, SHOT_MODEL__COLOUR_INDEX)
            shutter_item = self.shot_model.item(i, SHOT_MODEL__SHUTTER_INDEX)
            if item.checkState() == Qt.Checked:
                shot = item.data()
                colour_item_data = colour_item.data(Qt.UserRole)
                ticked_shots[shot] = (colour_item_data(), shutter_item.checkState())
        return ticked_shots

    def update_channels_treeview(self):
        ticked_shots = self.get_selected_shots_and_colours()

        # get set of channels
        channels = {}
        for shot in ticked_shots.keys():
            channels[shot] = set(shot.channels)
        channels_set = frozenset().union(*channels.values())

        # now find channels in channels_set which are not in the treeview, and add them
        # now find channels in channels set which are already in the treeview, but deactivated, and activate them
        treeview_channels_dict = {}
        deactivated_treeview_channels_dict = {}
        for i in range(self.channel_model.rowCount()):
            item = self.channel_model.item(i, CHANNEL_MODEL__CHECKBOX_INDEX)
            # Sanity check
            if unicode(item.text()) in treeview_channels_dict:
                raise RuntimeError("A duplicate channel name was detected in the treeview due to an internal error. Please lodge a bugreport detailing how the channels with the same name appeared in the channel treeview. Please restart the application")

            treeview_channels_dict[unicode(item.text())] = i
            if not item.isEnabled():
                deactivated_treeview_channels_dict[unicode(item.text())] = i
        treeview_channels = set(treeview_channels_dict.keys())
        deactivated_treeview_channels = set(deactivated_treeview_channels_dict.keys())

        # find list of channels to work with
        channels_to_add = channels_set.difference(treeview_channels)
        for channel in sorted(channels_to_add):
            items = []
            check_item = QStandardItem(channel)
            check_item.setEditable(False)
            check_item.setCheckable(True)
            check_item.setCheckState(Qt.Unchecked)
            items.append(check_item)
            # channel_name_item = QStandardItem(channel)
            # channel_name_item.setEditable(False)
            # items.append(channel_name_item)
            self.channel_model.appendRow(items)

        channels_to_reactivate = deactivated_treeview_channels.intersection(channels_set)
        for channel in channels_to_reactivate:
            for i in range(self.channel_model.columnCount()):
                item = self.channel_model.item(deactivated_treeview_channels_dict[channel], i)
                item.setEnabled(True)
                item.setSelectable(True)

        # now find channels in the treeview which are not in the channels_set and deactivate them
        channels_to_deactivate = treeview_channels.difference(channels_set)
        for channel in channels_to_deactivate:
            for i in range(self.channel_model.columnCount()):
                item = self.channel_model.item(treeview_channels_dict[channel], i)
                item.setEnabled(False)
                item.setSelectable(False)

        # TODO: Also update entries in groups

        self.update_plots()

    def update_plots(self):
        # get list of selected shots
        ticked_shots = self.get_selected_shots_and_colours()

        # SHould we rescale the x-axis?
        # if self._hidden_plot[0].getViewBox.getState()['autoRange'][0]:
        #    self._hidden_plot[0].enableAutoRange(axis=pg.ViewBox.XAxis)
        # else:
        #    self._hidden_plot[0].enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)

        # find stop time of longest ticked shot
        largest_stop_time = 0
        stop_time_set = False
        for shot in ticked_shots.keys():
            if shot.stop_time > largest_stop_time:
                largest_stop_time = shot.stop_time
                stop_time_set = True
        if not stop_time_set:
            largest_stop_time = 1.0

        # Update the range of the link plot
        self._hidden_plot[1].setData([0, largest_stop_time], [0, 1e-9])

        # Update plots
        for i in range(self.channel_model.rowCount()):
            check_item = self.channel_model.item(i, CHANNEL_MODEL__CHECKBOX_INDEX)
            channel = unicode(check_item.text())
            if check_item.checkState() == Qt.Checked and check_item.isEnabled():
                # we want to show this plot
                # does a plot already exist? If yes, show it
                if channel in self.plot_widgets:
                    self.plot_widgets[channel].show()
                    # update the plot
                    # are there are plot items for this channel which are shown that should not be?
                    to_delete = []
                    for shot in self.plot_items[channel]:
                        if shot not in ticked_shots.keys():
                            self.plot_widgets[channel].removeItem(self.plot_items[channel][shot])
                            # Remove Shutter Markers of unticked Shots
                            if shot in self.shutter_lines[channel]:
                                for line in self.shutter_lines[channel][shot][0]:
                                    self.plot_widgets[channel].removeItem(line)
                                for line in self.shutter_lines[channel][shot][1]:
                                    self.plot_widgets[channel].removeItem(line)
                                self.shutter_lines[channel].pop(shot)
                            to_delete.append(shot)
                    for shot in to_delete:
                        del self.plot_items[channel][shot]

                    # do we need to add any plot items for shots that were not previously selected?
                    for shot, (colour, shutters_checked) in ticked_shots.items():
                        if shot not in self.plot_items[channel]:
                            # plot_item = self.plot_widgets[channel].plot(shot.traces[channel][0], shot.traces[channel][1], pen=pg.mkPen(QColor(colour), width=2))
                            # Add empty plot as it the custom resampling we do will happen quicker if we don't attempt to first plot all of the data
                            plot_item = self.plot_widgets[channel].plot([0, 0], [0], pen=pg.mkPen(QColor(colour), width=2), stepMode=True)
                            self.plot_items[channel][shot] = plot_item

                        # Add Shutter Markers of newly ticked Shots
                        self.add_shutter_markers(shot, channel, shutters_checked)

                # If no, create one
                else:
                    self.create_plot(channel, ticked_shots)

            else:
                if channel not in self.plot_widgets:
                    self.create_plot(channel, ticked_shots)
                self.plot_widgets[channel].hide()

        self._resample = True

    def create_plot(self, channel, ticked_shots):
        self.plot_widgets[channel] = pg.PlotWidget()  # name=channel)
        self.plot_widgets[channel].setMinimumHeight(200)
        self.plot_widgets[channel].setMaximumHeight(200)
        self.plot_widgets[channel].setLabel('bottom', 'Time', units='s')
        self.plot_widgets[channel].showAxis('right', True)
        self.plot_widgets[channel].setXLink('runviewer - time axis link')
        self.plot_widgets[channel].sigXRangeChanged.connect(self.on_x_range_changed)
        self.ui.plot_layout.addWidget(self.plot_widgets[channel])
        self.shutter_lines[channel] = {}  # initialize Storage for shutter lines
        self.plot_items.setdefault(channel, {})

        has_units = False
        units = ''
        for shot, (colour, shutters_checked) in ticked_shots.items():
            if channel in shot.traces:
                # plot_item = self.plot_widgets[channel].plot(shot.traces[channel][0], shot.traces[channel][1], pen=pg.mkPen(QColor(colour), width=2))
                # Add empty plot as it the custom resampling we do will happen quicker if we don't attempt to first plot all of the data
                plot_item = self.plot_widgets[channel].plot([0, 0], [0], pen=pg.mkPen(QColor(colour), width=2), stepMode=True)
                self.plot_items[channel][shot] = plot_item

                if len(shot.traces[channel]) == 3:
                    has_units = True
                    units = shot.traces[channel][2]

                # Add Shutter Markers of ticked Shots
                self.add_shutter_markers(shot, channel, shutters_checked)

        if has_units:
            self.plot_widgets[channel].setLabel('left', channel, units=units)
        else:
            self.plot_widgets[channel].setLabel('left', channel)

    def add_shutter_markers(self, shot, channel, shutters_checked):
        if shot not in self.shutter_lines[channel] and channel in shot.shutter_times:
            self.shutter_lines[channel][shot] = [[], []]

            open_color = QColor(0, 255, 0)
            close_color = QColor(255, 0, 0)

            for t, val in shot.shutter_times[channel].items():
                scaled_t = t
                if val:  # val != 0, shutter open
                    line = self.plot_widgets[channel].addLine(x=scaled_t, pen=pg.mkPen(color=open_color, width=4., style=Qt.DotLine))
                    self.shutter_lines[channel][shot][1].append(line)
                    if not shutters_checked:
                        line.hide()
                else:  # else shutter close
                    line = self.plot_widgets[channel].addLine(x=scaled_t, pen=pg.mkPen(color=close_color, width=4., style=Qt.DotLine))
                    self.shutter_lines[channel][shot][0].append(line)
                    if not shutters_checked:
                        line.hide()

    def on_x_range_changed(self, *args):
        # print 'x range changed'
        self._resample = True

    @inmain_decorator(wait_for_return=True)
    def _get_resample_params(self, channel, shot):
        rect = self.plot_items[channel][shot].getViewBox().viewRect()
        xmin, xmax = rect.left(), rect.width() + rect.left()
        dx = xmax - xmin
        view_range = self.plot_widgets[channel].viewRange()
        return view_range[0][0], view_range[0][1], dx

    def resample(self, data_x, data_y, xmin, xmax, stop_time, num_pixels):
        """This is a function for downsampling the data before plotting
        it. Unlike using nearest neighbour interpolation, this method
        preserves the features of the plot. It chooses what value to
        use based on what values within a region are most different
        from the values it's already chosen. This way, spikes of a short
        duration won't just be skipped over as they would with any sort
        of interpolation."""
        # TODO: Only finely sample the currently visible region. Coarsely sample the rest
        # x_out = numpy.float32(numpy.linspace(data_x[0], data_x[-1], 4000*(data_x[-1]-data_x[0])/(xmax-xmin)))
        x_out = numpy.float64(numpy.linspace(xmin, xmax, 3 * 2000 + 2))
        y_out = numpy.empty(len(x_out) - 1, dtype=numpy.float64)
        data_x = numpy.float64(data_x)
        data_y = numpy.float64(data_y)

        # TODO: investigate only resampling when necessary.
        #       Currently pyqtgraph sometimes has trouble rendering things
        #       if you don't resample. If a point is far off the graph,
        #       and this point is the first that should be drawn for stepMode,
        #       because there is a long gap before the next point (which is
        #       visible) then there is a problem.
        #       Also need to explicitly handle cases where none of the data
        #       is visible (which resampling does by setting NaNs)
        #
        # x_data_slice = data_x[(data_x>=xmin)&(data_x<=xmax)]
        # print len(data_x)
        # if len(x_data_slice) < 3*2000+2:
        #    x_out = x_data_slice
        #    y_out = data_y[(data_x>=xmin)&(data_x<=xmax)][:-1]
        #    logger.info('skipping resampling')
        # else:
        resampling = True

        if resampling:
            _resample(data_x, data_y, x_out, y_out, numpy.float64(stop_time))
            # self.__resample4(data_x, data_y, x_out, y_out, numpy.float32(stop_time))
        else:
            x_out, y_out = data_x, data_y

        return x_out, y_out

    def __resample4(self, x_in, y_in, x_out, y_out, stop_time):
        # we want x-out to have three times the number of points as there are pixels
        # Plus one at the end
        # y_out = numpy.empty(len(x_out)-1, dtype=numpy.float64)
        # print 'len x_out: %d'%len(x_out)

        # A couple of special cases that I don't want to have to put extra checks in for:
        if x_out[-1] < x_in[0] or x_out[0] > stop_time:
            # We're all the way to the left of the data or all the way to the right. Fill with NaNs:
            y_out.fill('NaN')
        elif x_out[0] > x_in[-1]:
            # We're after the final clock tick, but before stop_time
            i = 0
            while i < len(x_out) - 1:
                if x_out[i] < stop_time:
                    y_out[i] = y_in[-1]
                else:
                    y_out[i] = numpy.float('NaN')
                i += 1
        else:
            i = 0
            j = 1
            # Until we get to the data, fill the output array with NaNs (which
            # get ignored when plotted)
            while x_out[i] < x_in[0]:
                y_out[i] = numpy.float('NaN')
                y_out[i + 1] = numpy.float('NaN')
                y_out[i + 2] = numpy.float('NaN')
                i += 3
            # If we're some way into the data, we need to skip ahead to where
            # we want to get the first datapoint from:
            while x_in[j] < x_out[i]:
                j += 1

            # Get the first datapoint:
            # y_out[i] = y_in[j-1]
            # i += 1

            # Get values until we get to the end of the data:
            while j < len(x_in) and i < len(x_out) - 2:  # Leave one spare for the final data point and one because stepMode=True requires len(y)=len(x)-1
                # This is 'nearest neighbour on the left' interpolation. It's
                # what we want if none of the source values checked in the
                # upcoming loop are used:
                y_out[i] = y_in[j - 1]
                i += 2
                positive_jump_value = 0
                positive_jump_index = j - 1
                negative_jump_value = 0
                negative_jump_index = j - 1
                # now find the max and min values between this x_out time point and the next x_out timepoint
                # print i
                while j < len(x_in) and x_in[j] < x_out[i]:
                    jump = y_in[j] - y_out[i - 2]
                    # would using this source value cause a bigger positive jump?
                    if jump > 0 and jump > positive_jump_value:
                        positive_jump_value = jump
                        positive_jump_index = j
                    # would using this source value cause a bigger negative jump?
                    elif jump < 0 and jump < negative_jump_value:
                        negative_jump_value = jump
                        negative_jump_index = j

                    j += 1

                if positive_jump_index < negative_jump_index:
                    y_out[i - 1] = y_in[positive_jump_index]
                    y_out[i] = y_in[negative_jump_index]
                    # TODO: We could override the x_out values with x_in[jump_index]
                else:
                    y_out[i - 1] = y_in[negative_jump_index]
                    y_out[i] = y_in[positive_jump_index]

                i += 1

            # Get the last datapoint:
            if j < len(x_in):
                # If the sample rate of the raw data is low, then the current
                # j point could be outside the current plot view range
                # If so, decrease j so that we take a value that is within the
                # plot view range.
                if x_in[j] > x_out[-1] and j > 0:
                    j -= 1

                y_out[i] = y_in[j]
                i += 1
            # if i < len(x_out):
            #    y_out[i] = y_in[-1]
            #    i += 1
            # Fill the remainder of the array with the last datapoint,
            # if t < stop_time, and then NaNs after that:
            while i < len(x_out) - 1:
                if x_out[i] < stop_time:
                    y_out[i] = y_in[-1]
                else:
                    y_out[i] = numpy.float('NaN')
                i += 1
        # return y_out # method changed to modify y_out array in place

    def __resample3(self, x_in, y_in, x_out, stop_time):
        """This is a Python implementation of the C extension. For
        debugging and developing the C extension."""
        y_out = numpy.empty(len(x_out))
        i = 0
        j = 1
        # A couple of special cases that I don't want to have to put extra checks in for:
        if x_out[-1] < x_in[0] or x_out[0] > stop_time:
            # We're all the way to the left of the data or all the way to the right. Fill with NaNs:
            while i < len(x_out):
                y_out[i] = numpy.float('NaN')
                i += 1
        elif x_out[0] > x_in[-1]:
            # We're after the final clock tick, but before stop_time
            while i < len(x_out):
                if x_out[i] < stop_time:
                    y_out[i] = y_in[-1]
                else:
                    y_out[i] = numpy.float('NaN')
                i += 1
        else:
            # Until we get to the data, fill the output array with NaNs (which
            # get ignored when plotted)
            while x_out[i] < x_in[0]:
                y_out[i] = numpy.float('NaN')
                i += 1
            # If we're some way into the data, we need to skip ahead to where
            # we want to get the first datapoint from:
            while x_in[j] < x_out[i]:
                j += 1
            # Get the first datapoint:
            y_out[i] = y_in[j - 1]
            i += 1
            # Get values until we get to the end of the data:
            while j < len(x_in) and i < len(x_out):
                # This is 'nearest neighbour on the left' interpolation. It's
                # what we want if none of the source values checked in the
                # upcoming loop are used:
                y_out[i] = y_in[j - 1]
                while j < len(x_in) and x_in[j] < x_out[i]:
                    # Would using this source value cause the interpolated values
                    # to make a bigger jump?
                    if numpy.abs(y_in[j] - y_out[i - 1]) > numpy.abs(y_out[i] - y_out[i - 1]):
                        # If so, use this source value:
                        y_out[i] = y_in[j]
                    j += 1
                i += 1
            # Get the last datapoint:
            if i < len(x_out):
                y_out[i] = y_in[-1]
                i += 1
            # Fill the remainder of the array with the last datapoint,
            # if t < stop_time, and then NaNs after that:
            while i < len(x_out):
                if x_out[i] < stop_time:
                    y_out[i] = y_in[-1]
                else:
                    y_out[i] = numpy.float('NaN')
                i += 1
        return y_out

    def _resample_thread(self):
        logger = logging.getLogger('runviewer.resample_thread')
        while True:
            if self._resample:
                self._resample = False
                # print 'resampling'
                ticked_shots = inmain(self.get_selected_shots_and_colours)
                for shot, (colour, shutters_checked) in ticked_shots.items():
                    for channel in shot.traces:
                        if self.channel_checked_and_enabled(channel):
                            try:
                                xmin, xmax, dx = self._get_resample_params(channel, shot)

                                # We go a bit outside the visible range so that scrolling
                                # doesn't immediately go off the edge of the data, and the
                                # next resampling might have time to fill in more data before
                                # the user sees any empty space.
                                xnew, ynew = self.resample(shot.traces[channel][0], shot.traces[channel][1], xmin, xmax, shot.stop_time, dx)
                                inmain(self.plot_items[channel][shot].setData, xnew, ynew, pen=pg.mkPen(QColor(colour), width=2), stepMode=True)
                            except Exception:
                                #self._resample = True
                                pass
                        else:
                            logger.info('ignoring channel %s' % channel)
            time.sleep(0.5)

    @inmain_decorator(wait_for_return=True)
    def channel_checked_and_enabled(self, channel):
        logger.info('is channel %s enabled' % channel)
        index = self.channel_model.index(0, CHANNEL_MODEL__CHANNEL_INDEX)
        indexes = self.channel_model.match(index, Qt.DisplayRole, channel, 1, Qt.MatchExactly)
        logger.info('number of matches %d' % len(indexes))
        if len(indexes) == 1:
            check_item = self.channel_model.itemFromIndex(indexes[0])
            if check_item.checkState() == Qt.Checked and check_item.isEnabled():
                return True
        return False

    def on_x_axis_reset(self):
        self._hidden_plot[0].enableAutoRange(axis=pg.ViewBox.XAxis)

    def on_y_axes_reset(self):
        for plot_widget in self.plot_widgets.values():
            plot_widget.enableAutoRange(axis=pg.ViewBox.YAxis)

    def _enable_selected_shots(self):
        self.update_ticks_of_selected_shots(Qt.Checked)

    def _disable_selected_shots(self):
        self.update_ticks_of_selected_shots(Qt.Unchecked)

    def update_ticks_of_selected_shots(self, state):
        # Get the selection model from the treeview
        selection_model = self.ui.shot_treeview.selectionModel()
        # Create a list of select row indices
        selected_row_list = [index.row() for index in sorted(selection_model.selectedRows())]
        # for each row selected
        for row in selected_row_list:
            check_item = self.shot_model.item(row, SHOT_MODEL__CHECKBOX_INDEX)
            check_item.setCheckState(state)

    def _move_up(self):
        # Get the selection model from the treeview
        selection_model = self.ui.channel_treeview.selectionModel()
        # Create a list of select row indices
        selected_row_list = [index.row() for index in sorted(selection_model.selectedRows())]
        # For each row selected
        for i, row in enumerate(selected_row_list):
            # only move the row if it is not element 0, and the row above it is not selected
            # (note that while a row above may have been initially selected, it should by now, be one row higher
            # since we start moving elements of the list upwards starting from the lowest index)
            if row > 0 and (row - 1) not in selected_row_list:
                # Remove the selected row
                items = self.channel_model.takeRow(row)
                # Add the selected row into a position one above
                self.channel_model.insertRow(row - 1, items)
                # Since it is now a newly inserted row, select it again
                selection_model.select(self.channel_model.indexFromItem(items[0]), QItemSelectionModel.SelectCurrent)
                # reupdate the list of selected indices to reflect this change
                selected_row_list[i] -= 1
        self.update_plot_positions()

    def _move_down(self):
        # Get the selection model from the treeview
        selection_model = self.ui.channel_treeview.selectionModel()
        # Create a list of select row indices
        selected_row_list = [index.row() for index in reversed(sorted(selection_model.selectedRows()))]
        # For each row selected
        for i, row in enumerate(selected_row_list):
            # only move the row if it is not the last element, and the row above it is not selected
            # (note that while a row below may have been initially selected, it should by now, be one row lower
            # since we start moving elements of the list upwards starting from the highest index)
            if row < self.channel_model.rowCount() - 1 and (row + 1) not in selected_row_list:
                # Remove the selected row
                items = self.channel_model.takeRow(row)
                # Add the selected row into a position one above
                self.channel_model.insertRow(row + 1, items)
                # Since it is now a newly inserted row, select it again
                selection_model.select(self.channel_model.indexFromItem(items[0]), QItemSelectionModel.SelectCurrent)
                # reupdate the list of selected indices to reflect this change
                selected_row_list[i] += 1
        self.update_plot_positions()

    def _move_top(self):
        # Get the selection model from the treeview
        selection_model = self.ui.channel_treeview.selectionModel()
        # Create a list of select row indices
        selected_row_list = [index.row() for index in sorted(selection_model.selectedRows())]
        # For each row selected
        for i, row in enumerate(selected_row_list):
            # only move the row while it is not element 0, and the row above it is not selected
            # (note that while a row above may have been initially selected, it should by now, be one row higher
            # since we start moving elements of the list upwards starting from the lowest index)
            while row > 0 and (row - 1) not in selected_row_list:
                # Remove the selected row
                items = self.channel_model.takeRow(row)
                # Add the selected row into a position one above
                self.channel_model.insertRow(row - 1, items)
                # Since it is now a newly inserted row, select it again
                selection_model.select(self.channel_model.indexFromItem(items[0]), QItemSelectionModel.SelectCurrent)
                # reupdate the list of selected indices to reflect this change
                selected_row_list[i] -= 1
                row -= 1
        self.update_plot_positions()

    def _move_bottom(self):
        selection_model = self.ui.channel_treeview.selectionModel()
        # Create a list of select row indices
        selected_row_list = [index.row() for index in reversed(sorted(selection_model.selectedRows()))]
        # For each row selected
        for i, row in enumerate(selected_row_list):
            # only move the row while it is not the last element, and the row above it is not selected
            # (note that while a row below may have been initially selected, it should by now, be one row lower
            # since we start moving elements of the list upwards starting from the highest index)
            while row < self.channel_model.rowCount() - 1 and (row + 1) not in selected_row_list:
                # Remove the selected row
                items = self.channel_model.takeRow(row)
                # Add the selected row into a position one above
                self.channel_model.insertRow(row + 1, items)
                # Since it is now a newly inserted row, select it again
                selection_model.select(self.channel_model.indexFromItem(items[0]), QItemSelectionModel.SelectCurrent)
                # reupdate the list of selected indices to reflect this change
                selected_row_list[i] += 1
                row += 1
        self.update_plot_positions()

    def update_plot_positions(self):
        # remove all widgets
        layout_items = {}
        for i in range(self.ui.plot_layout.count()):
            if i == 0:
                continue
            item = self.ui.plot_layout.takeAt(i)

        # add all widgets
        for i in range(self.channel_model.rowCount()):
            check_item = self.channel_model.item(i, CHANNEL_MODEL__CHECKBOX_INDEX)
            channel = unicode(check_item.text())
            if channel in self.plot_widgets:
                self.ui.plot_layout.addWidget(self.plot_widgets[channel])
                if check_item.checkState() == Qt.Checked and check_item.isEnabled():
                    self.plot_widgets[channel].show()
                else:
                    self.plot_widgets[channel].hide()


class Shot(object):
    def __init__(self, path):
        self.path = path

        # Store list of traces
        self._traces = None
        # store list of channels
        self._channels = None

        # store list of shutter changes and callibrations
        self._shutter_times = None
        self._shutter_calibrations = {}

        # TODO: Get this dynamically
        device_list = ['PulseBlaster', 'NI_PCIe_6363', 'NI_PCI_6733']

        # Load connection table
        self.connection_table = ConnectionTable(path)

        # open h5 file
        with h5py.File(path, 'r') as file:
            # Get master pseudoclock
            self.master_pseudoclock_name = file['connection table'].attrs['master_pseudoclock']

            # get stop time
            self.stop_time = file['devices/%s' % self.master_pseudoclock_name].attrs['stop_time']

            self.device_names = file['devices'].keys()

            # Get Shutter Calibrations
            if 'calibrations' in file and 'Shutter' in file['calibrations']:
                for name, open_delay, close_delay in numpy.array(file['calibrations']['Shutter']):
                    self._shutter_calibrations[name] = [open_delay, close_delay]

    def delete_cache(self):
        self._channels = None
        self._traces = None

    def _load(self):
        if self._channels is None:
            self._channels = {}
        if self._traces is None:
            self._traces = {}
        if self._shutter_times is None:
            self._shutter_times = {}

        # Let's walk the connection table, starting with the master pseudoclock
        master_pseudoclock_device = self.connection_table.find_by_name(self.master_pseudoclock_name)

        self._load_device(master_pseudoclock_device)

    def add_trace(self, name, trace, parent_device_name, connection):
        name = unicode(name)
        self._channels[name] = {'device_name': parent_device_name, 'port': connection}
        self._traces[name] = trace

    # Temporary solution to physical shutter times
    def add_shutter_times(self, shutters):
        for name, open_state in shutters:
            x_values, y_values = self._traces[name]
            if len(x_values) > 0:
                change_indices = numpy.where(y_values[:-1] != y_values[1:])[0]
                change_indices += 1 # use the index of the value that is changed to
                change_values = zip(x_values[change_indices], y_values[change_indices])
                change_values.insert(0, (x_values[0], y_values[0])) # insert first value
                self._shutter_times[name] = {x_value + (self._shutter_calibrations[name][0] if y_value == open_state else self._shutter_calibrations[name][1]): 1 if y_value == open_state else 0 for x_value, y_value in change_values}

    def _load_device(self, device, clock=None):
        try:
            print 'loading %s' % device.name
            module = device.device_class
            # Load the master pseudoclock class
            # labscript_devices.import_device(module)
            device_class = labscript_devices.get_runviewer_parser(module)
            device_instance = device_class(self.path, device)
            clocklines_and_triggers = device_instance.get_traces(self.add_trace, clock)

            for name, trace in clocklines_and_triggers.items():
                child_device = self.connection_table.find_by_name(name)
                for grandchild_device_name, grandchild_device in child_device.child_list.items():
                    self._load_device(grandchild_device, trace)

        except Exception:
            # TODO: print/log exception traceback
            # if device.name == 'ni_card_0' or device.name == 'pulseblaster_0' or device.name == 'pineblaster_0' or device.name == 'ni_card_1' or device.name == 'novatechdds9m_0':
            #    raise
            # raise
            if hasattr(device, 'name'):
                print 'Failed to load device %s' % device.name
            else:
                print 'Failed to load device (unknown name, device object does not have attribute name)'

        # get all Shutters with their open_state
        try:
            shutters = [(name, child_con.properties['open_state']) for name, child_con in device.child_list.items() if child_con.device_class == "Shutter"]
        except KeyError:
            # no openstate in connection table
            with h5py.File(self.path, 'r') as file:
                if "runviewer" in file:
                    if "shutter_times" in file["runviewer"]:
                        for name, val in file["runviewer"]["shutter_times"].attrs.items():
                            self._shutter_times[name] = {float(key_value.split(":")[0]): int(key_value.split(":")[1]) for key_value in val.strip('{}}').split(",")}
            pass
        else:
            self.add_shutter_times(shutters)

    @property
    def channels(self):
        if self._channels is None:
            self._load()

        return self._channels.keys()

    def clear_cache(self):
        # clear cache variables to cut down on memory usage
        pass

    @property
    def traces(self):
        # if traces cached:
        #    return cached traces and waits
        if self._traces is None:
            self._load()
        return self._traces

    @property
    def shutter_times(self):
        if self._shutter_times is None:
            self._load()
        return self._shutter_times


class TempShot(Shot):
    def __init__(self, i):
        Shot.__init__(self, 'shot %d' % i)
        self._channels = ['Bx', 'By', 'Bz', 'Bq']

        self.stop_time = i + 1

        self.traces = {}
        no_x_points = 10000
        for channel in self.channels:
            # self.traces[channel] = (numpy.linspace(0,10,no_x_points), numpy.random.rand(no_x_points))
            x_points = numpy.linspace(0, self.stop_time, no_x_points)
            self.traces[channel] = (x_points, (i + 1) * numpy.sin(x_points * numpy.pi + i / 11.0 * 2 * numpy.pi))

    @property
    def channels(self):
        return self._channels

    def get_traces(self):
        return self.traces


class RunviewerServer(ZMQServer):
    def __init__(self, *args, **kwargs):
        ZMQServer.__init__(self, *args, **kwargs)
        self.logger = logging.getLogger('runviewer.server')

    def handler(self, h5_filepath):
        if h5_filepath == 'hello':
            return 'hello'

        self.logger.info('Received hdf5 file: %s' % h5_filepath)
        # Convert path to local slashes and shared drive prefix:
        h5_filepath = labscript_utils.shared_drive.path_to_local(h5_filepath)
        logger.info('local filepath: %s' % h5_filepath)
        # we add the shot to a queue so that we don't have to wait for the app to come up before
        # responding to runmanager
        shots_to_process_queue.put(h5_filepath)
        return 'ok'


if __name__ == "__main__":
    qapplication = QApplication(sys.argv)

    shots_to_process_queue = Queue()

    exp_config = LabConfig(required_params = {"DEFAULT": ["experiment_name"], "paths": ["shared_drive", "experiment_shot_storage"], 'ports': ['runviewer']})

    port = int(exp_config.get('ports', 'runviewer'))
    myappid = 'monashbec.runviewer'  # arbitrary string
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except:
        logger.info('Not on a windows machine')
    # Start experiment server
    experiment_server = RunviewerServer(port)

    app = RunViewer(exp_config)

    def execute_program():
        qapplication.exec_()

    sys.exit(execute_program())
