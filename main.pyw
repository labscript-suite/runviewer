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

import zprocess.locking, labscript_utils.h5_lock, h5py
zprocess.locking.set_client_process_name('runviewer')
from PySide.QtCore import *
from PySide.QtGui import *
from PySide.QtUiTools import QUiLoader
import numpy

# must be imported after PySide
import pyqtgraph as pg
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')

import labscript_utils.excepthook
from qtutils import *
from blacs.connections import ConnectionTable
import labscript_devices

from resample import resample as _resample

SHOT_MODEL__COLOUR_INDEX = 0
SHOT_MODEL__CHECKBOX_INDEX = 1
SHOT_MODEL__PATH_INDEX = 1
CHANNEL_MODEL__CHECKBOX_INDEX = 0
CHANNEL_MODEL__CHANNEL_INDEX = 0

# stupid hack to work around the fact that PySide screws with the type of a variable when it goes into a model. Enums are converted to ints, which then
# can't be interpreted by QColor correctly (for example)
# unfortunately Qt doesn't provide a python list structure of enums, so you have to build the list yourself.
def int_to_enum(enum_list, value):
    for item in enum_list:
        if item == value:
            return item

class ColourDelegate(QItemDelegate):

    def __init__(self, view, *args, **kwargs):
        QItemDelegate.__init__(self, *args, **kwargs)
        self._view = view
        self._colours = [Qt.black, Qt.red,  Qt.green, Qt.blue, Qt.cyan, Qt.magenta, Qt.yellow, Qt.gray, Qt.darkRed, Qt.darkGreen, Qt.darkBlue, Qt.darkCyan, Qt.darkMagenta, Qt.darkYellow, Qt.darkGray, Qt.lightGray]

        self._current_colour_index = 0
        
    def get_next_colour(self):
        colour = self._colours[self._current_colour_index]
        self._current_colour_index +=1
        if self._current_colour_index >= len(self._colours):
            self._current_colour_index = 0
        return colour
        
    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        #colours = QColor.colorNames()
        for colour in self._colours:
            pixmap = QPixmap(20,20)
            pixmap.fill(colour)
            editor.addItem(QIcon(pixmap),'', colour)
        
        editor.activated.connect(lambda index, editor=editor: self._view.commitData(editor))
        editor.activated.connect(lambda index, editor=editor: self._view.closeEditor(editor,QAbstractItemDelegate.NoHint))
        QTimer.singleShot(10,editor.showPopup)
        
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
        model.setData(index,lambda clist=self._colours,colour=colour:int_to_enum(clist,colour), Qt.UserRole)
        
    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect);

        
class RunViewer(object):
    def __init__(self):
        self.ui = QUiLoader().load(os.path.join(os.path.dirname(os.path.realpath(__file__)),'main.ui'))
        
        #setup shot treeview model
        self.shot_model = QStandardItemModel()
        self.shot_model.setHorizontalHeaderLabels(['colour','path'])
        self.ui.shot_treeview.setModel(self.shot_model)
        self.shot_model.itemChanged.connect(self.on_shot_selection_changed)
        self.shot_colour_delegate = ColourDelegate(self.ui.shot_treeview)
        self.ui.shot_treeview.setItemDelegateForColumn(0, self.shot_colour_delegate)
        
        #setup channel treeview model
        self.channel_model = QStandardItemModel()
        self.channel_model.setHorizontalHeaderLabels(['channel'])
        self.ui.channel_treeview.setModel(self.channel_model)
        self.channel_model.itemChanged.connect(self.update_plots)
        
        # create a hidden plot widget that all plots can link their x-axis too
        hidden_plot = pg.PlotWidget(name='runviewer - time axis link')
        
        hidden_plot.setMinimumHeight(40)
        hidden_plot.setMaximumHeight(40)
        hidden_plot.setLabel('bottom', 'Time', units='s')
        hidden_plot.showAxis('right', True)
        hidden_plot_item = hidden_plot.plot([0,1],[0,0])
        self._hidden_plot = (hidden_plot, hidden_plot_item)
        self.ui.plot_layout.addWidget(hidden_plot)
        
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
        
        
        self.ui.show()
        
        # internal variables
        #self._channels_list = {}
        self.plot_widgets = {}
        self.plot_items = {}
        
        # start resample thread
        self._resample = False
        self._thread = threading.Thread(target=self._resample_thread)
        self._thread.daemon = True
        self._thread.start()
        
        # self.temp_load_shots()
        shot = Shot(r'C:\Users\Phil\Documents\Programming\labscript_suite\labscript\example.h5')
        self.load_shot(shot)
    
    def on_add_shot(self):
        dialog = QFileDialog(self.ui,"Select file to load", r'C:\Users\Phil\Documents\Programming\labscript_suite\labscript', "HDF5 files (*.h5 *.hdf5)")
        dialog.setViewMode(QFileDialog.Detail)
        dialog.setFileMode(QFileDialog.ExistingFile)
        if dialog.exec_():
            selected_files = dialog.selectedFiles()
            popup_warning = False
            for file in selected_files:
                try:
                    filepath = str(file)
                    # Qt has this weird behaviour where if you type in the name of a file that exists
                    # but does not have the extension you have limited the dialog to, the OK button is greyed out
                    # but you can hit enter and the file will be selected. 
                    # So we must check the extension of each file here!
                    if filepath.endswith('.h5') or filepath.endswith('.hdf5'):
                        shot = Shot(filepath)
                        self.load_shot(shot)
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
            colour_item = self.shot_model.item(row,SHOT_MODEL__COLOUR_INDEX)
            
            if checked:
                colour = self.shot_colour_delegate.get_next_colour()
                colour_item.setEditable(True)
                pixmap = QPixmap(20,20)
                pixmap.fill(colour)
                icon = QIcon(pixmap)
            else:
                colour = None
                icon = None
                colour_item.setEditable(False)
                
            colour_item.setData(icon, Qt.DecorationRole)
            colour_item.setData(lambda clist=self.shot_colour_delegate._colours,colour=colour:int_to_enum(clist,colour), Qt.UserRole)
            
            # model.setData(index, editor.itemIcon(editor.currentIndex()), 
            # model.setData(index, editor.itemData(editor.currentIndex()), Qt.UserRole)
            
            
        
            self.update_channels_treeview()
        elif self.shot_model.indexFromItem(item).column() == SHOT_MODEL__COLOUR_INDEX:
            #update the plot colours
            
            # get reference to the changed shot
            current_shot = self.shot_model.item(self.shot_model.indexFromItem(item).row(),SHOT_MODEL__CHECKBOX_INDEX).data()
            
            # find and update the pen of the plot items
            for channel in self.plot_items.keys():
                for shot in self.plot_items[channel]:
                    if shot == current_shot:
                        self.plot_items[channel][shot].setPen(pg.mkPen(QColor(item.data(Qt.UserRole)()), width=2))
            
    def load_shot(self, shot):
        # add shot to shot list
        # Create Items
        items = []
        colour_item = QStandardItem('')
        colour_item.setEditable(False)
        colour_item.setToolTip('Double-click to change colour')
        items.append(colour_item)
        
        check_item = QStandardItem(shot.path)
        check_item.setEditable(False)
        check_item.setCheckable(True)
        check_item.setCheckState(Qt.Unchecked) # options are Qt.Checked OR Qt.Unchecked        
        check_item.setData(shot)
        items.append(check_item)
        # script name
        # path_item = QStandardItem(shot.path)
        # path_item.setEditable(False)
        # items.append(path_item)
        self.shot_model.appendRow(items)
        
        # only do this if we are checking the shot we are adding
        #self.update_channels_treeview()
        
    def get_selected_shots_and_colours(self):
        # get the ticked shots  
        ticked_shots = {}
        for i in range(self.shot_model.rowCount()):
            item = self.shot_model.item(i,SHOT_MODEL__CHECKBOX_INDEX)
            colour_item = self.shot_model.item(i,SHOT_MODEL__COLOUR_INDEX)
            if item.checkState() == Qt.Checked:
                ticked_shots[item.data()] = colour_item.data(Qt.UserRole)()
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
            item = self.channel_model.item(i,CHANNEL_MODEL__CHECKBOX_INDEX)
            # Sanity check
            if item.text() in treeview_channels_dict:
                raise RuntimeError("A duplicate channel name was detected in the treeview due to an internal error. Please lodge a bugreport detailing how the channels with the same name appeared in the channel treeview. Please restart the application")
                
            treeview_channels_dict[item.text()] = i
            if not item.isEnabled():
                deactivated_treeview_channels_dict[item.text()] = i
        treeview_channels = set(treeview_channels_dict.keys())
        deactivated_treeview_channels = set(deactivated_treeview_channels_dict.keys()) 
        
        # find list of channels to work with
        channels_to_add = channels_set.difference(treeview_channels)
        for channel in channels_to_add:
            items = []
            check_item = QStandardItem(channel)
            check_item.setEditable(False)
            check_item.setCheckable(True)
            check_item.setCheckState(Qt.Checked)
            items.append(check_item)
            # channel_name_item = QStandardItem(channel)
            # channel_name_item.setEditable(False)
            # items.append(channel_name_item)
            self.channel_model.appendRow(items)
            
        channels_to_reactivate = deactivated_treeview_channels.intersection(channels_set)
        for channel in channels_to_reactivate:
            for i in range(self.channel_model.columnCount()):
                item = self.channel_model.item(deactivated_treeview_channels_dict[channel],i)
                item.setEnabled(True)
                item.setSelectable(True)
        
        # now find channels in the treeview which are not in the channels_set and deactivate them
        channels_to_deactivate = treeview_channels.difference(channels_set)
        for channel in channels_to_deactivate:
            for i in range(self.channel_model.columnCount()):
                item = self.channel_model.item(treeview_channels_dict[channel],i)
                item.setEnabled(False)
                item.setSelectable(False)
        
        # TODO: Also update entries in groups
        
        self.update_plots()
        
    def update_plots(self):
        # get list of selected shots
        ticked_shots = self.get_selected_shots_and_colours()
        
        # SHould we rescale the x-axis?
        # if self._hidden_plot[0].getViewBox.getState()['autoRange'][0]:
            # self._hidden_plot[0].enableAutoRange(axis=pg.ViewBox.XAxis)
        # else:
            # self._hidden_plot[0].enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)
            
        # find stop time of longest ticked shot
        largest_stop_time = 0
        stop_time_set = False
        for shot in ticked_shots.keys():
            if shot.stop_time > largest_stop_time:
                largest_stop_time = shot.stop_time
                stop_time_set = True
        if not stop_time_set:
            largest_stop_time = 1.0
        
        #Update the range of the link plot
        self._hidden_plot[1].setData([0,largest_stop_time],[0,1e-9])
        
        # Update plots
        for i in range(self.channel_model.rowCount()):
            check_item = self.channel_model.item(i,CHANNEL_MODEL__CHECKBOX_INDEX)
            channel = check_item.text()
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
                            to_delete.append(shot)
                    for shot in to_delete:
                        del self.plot_items[channel][shot]
                    
                    # do we need to add any plot items for shots that were not previously selected?
                    for shot, colour in ticked_shots.items():
                        if shot not in self.plot_items[channel]:
                            plot_item = self.plot_widgets[channel].plot(shot.traces[channel][0], shot.traces[channel][1], pen=pg.mkPen(QColor(colour), width=2))
                            self.plot_items[channel][shot] = plot_item
                    
                # If no, create one
                else:
                    self.plot_widgets[channel] = pg.PlotWidget(name=channel)
                    self.plot_widgets[channel].setMinimumHeight(200)
                    self.plot_widgets[channel].setMaximumHeight(200)
                    self.plot_widgets[channel].setLabel('left', channel, units='V')
                    self.plot_widgets[channel].setLabel('bottom', 'Time', units='s')
                    self.plot_widgets[channel].showAxis('right', True)
                    self.plot_widgets[channel].setXLink('runviewer - time axis link') 
                    self.plot_widgets[channel].sigXRangeChanged.connect(self.on_x_range_changed)                     
                    self.ui.plot_layout.addWidget(self.plot_widgets[channel])
                    
                    for shot, colour in ticked_shots.items():
                        if channel in shot.traces:
                            plot_item = self.plot_widgets[channel].plot(shot.traces[channel][0], shot.traces[channel][1], pen=pg.mkPen(QColor(colour), width=2))
                            self.plot_items.setdefault(channel, {})
                            self.plot_items[channel][shot] = plot_item
                
            else:
                if channel in self.plot_widgets:
                    self.plot_widgets[channel].hide()

    def on_x_range_changed(self, *args):
        # print 'x range changed'
        self._resample = True
        
    @inmain_decorator(wait_for_return=True)
    def _get_resample_params(self, channel, shot):
        rect = self.plot_items[channel][shot].getViewBox().viewRect()
        xmin, xmax = rect.left(), rect.width() + rect.left()
        dx = xmax - xmin
        return xmin, xmax, dx
    
    def resample(self,data_x, data_y, xmin, xmax, stop_time):
        """This is a function for downsampling the data before plotting
        it. Unlike using nearest neighbour interpolation, this method
        preserves the features of the plot. It chooses what value to
        use based on what values within a region are most different
        from the values it's already chosen. This way, spikes of a short
        duration won't just be skipped over as they would with any sort
        of interpolation."""
        x_out = numpy.float32(numpy.linspace(xmin, xmax, 4000))
        y_out = numpy.empty(len(x_out), dtype=numpy.float32)
        data_x = numpy.float32(data_x)
        data_y = numpy.float32(data_y)
        _resample(data_x, data_y, x_out, y_out, numpy.float32(stop_time))
        # y_out = self.__resample3(data_x, data_y, x_out,numpy.float32(stop_time))
        return x_out, y_out
    
    def __resample3(self,x_in,y_in,x_out, stop_time):
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
            y_out[i] = y_in[j-1]
            i += 1
            # Get values until we get to the end of the data:
            while j < len(x_in) and i < len(x_out):
                # This is 'nearest neighbour on the left' interpolation. It's
                # what we want if none of the source values checked in the
                # upcoming loop are used:
                y_out[i] = y_in[j-1]
                while j < len(x_in) and x_in[j] < x_out[i]:
                    # Would using this source value cause the interpolated values
                    # to make a bigger jump?
                    if numpy.abs(y_in[j] - y_out[i-1]) > numpy.abs(y_out[i] - y_out[i-1]):
                        # If so, use this source value:
                        y_out[i] = y_in[j]
                    j+=1
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
        while True:
            if self._resample:
                self._resample = False
                # print 'resampling'
                ticked_shots = inmain(self.get_selected_shots_and_colours)
                for shot, colour in ticked_shots.items():
                    for channel in shot.traces:
                        xmin, xmax, dx = self._get_resample_params(channel,shot)
                        
                        # We go a bit outside the visible range so that scrolling
                        # doesn't immediately go off the edge of the data, and the
                        # next resampling might have time to fill in more data before
                        # the user sees any empty space.
                        xnew, ynew = self.resample(shot.traces[channel][0], shot.traces[channel][1], xmin-0.2*dx, xmax+0.2*dx, shot.stop_time)
                        inmain(self.plot_items[channel][shot].setData, xnew, ynew, pen=pg.mkPen(QColor(colour), width=2))
                        
            time.sleep(0.5)
            
    def on_x_axis_reset(self):
        self._hidden_plot[0].enableAutoRange(axis=pg.ViewBox.XAxis)   
        
    def on_y_axes_reset(self):
        for plot_widget in self.plot_widgets.values():
            plot_widget.enableAutoRange(axis=pg.ViewBox.YAxis)
           
    def temp_load_shots(self):
        for i in range(10):
            shot = TempShot(i)
            self.load_shot(shot)
    
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
            check_item = self.shot_model.item(row,SHOT_MODEL__CHECKBOX_INDEX)
            check_item.setCheckState(state)
    
    def _move_up(self):        
        # Get the selection model from the treeview
        selection_model = self.ui.channel_treeview.selectionModel()    
        # Create a list of select row indices
        selected_row_list = [index.row() for index in sorted(selection_model.selectedRows())]
        # For each row selected
        for i,row in enumerate(selected_row_list):
            # only move the row if it is not element 0, and the row above it is not selected
            # (note that while a row above may have been initially selected, it should by now, be one row higher
            # since we start moving elements of the list upwards starting from the lowest index)
            if row > 0 and (row-1) not in selected_row_list:
                # Remove the selected row
                items = self.channel_model.takeRow(row)
                # Add the selected row into a position one above
                self.channel_model.insertRow(row-1,items)
                # Since it is now a newly inserted row, select it again
                selection_model.select(self.channel_model.indexFromItem(items[0]),QItemSelectionModel.SelectCurrent)
                # reupdate the list of selected indices to reflect this change
                selected_row_list[i] -= 1
        self.update_plot_positions()
       
    def _move_down(self):
        # Get the selection model from the treeview
        selection_model = self.ui.channel_treeview.selectionModel()    
        # Create a list of select row indices
        selected_row_list = [index.row() for index in reversed(sorted(selection_model.selectedRows()))]
        # For each row selected
        for i,row in enumerate(selected_row_list):
            # only move the row if it is not the last element, and the row above it is not selected
            # (note that while a row below may have been initially selected, it should by now, be one row lower
            # since we start moving elements of the list upwards starting from the highest index)
            if row < self.channel_model.rowCount()-1 and (row+1) not in selected_row_list:
                # Remove the selected row
                items = self.channel_model.takeRow(row)
                # Add the selected row into a position one above
                self.channel_model.insertRow(row+1,items)
                # Since it is now a newly inserted row, select it again
                selection_model.select(self.channel_model.indexFromItem(items[0]),QItemSelectionModel.SelectCurrent)
                # reupdate the list of selected indices to reflect this change
                selected_row_list[i] += 1
        self.update_plot_positions()
        
    def _move_top(self):
        # Get the selection model from the treeview
        selection_model = self.ui.channel_treeview.selectionModel()    
        # Create a list of select row indices
        selected_row_list = [index.row() for index in sorted(selection_model.selectedRows())]
        # For each row selected
        for i,row in enumerate(selected_row_list):
            # only move the row while it is not element 0, and the row above it is not selected
            # (note that while a row above may have been initially selected, it should by now, be one row higher
            # since we start moving elements of the list upwards starting from the lowest index)
            while row > 0 and (row-1) not in selected_row_list:
                # Remove the selected row
                items = self.channel_model.takeRow(row)
                # Add the selected row into a position one above
                self.channel_model.insertRow(row-1,items)
                # Since it is now a newly inserted row, select it again
                selection_model.select(self.channel_model.indexFromItem(items[0]),QItemSelectionModel.SelectCurrent)
                # reupdate the list of selected indices to reflect this change
                selected_row_list[i] -= 1
                row -= 1
        self.update_plot_positions()
              
    def _move_bottom(self):
        selection_model = self.ui.channel_treeview.selectionModel()    
        # Create a list of select row indices
        selected_row_list = [index.row() for index in reversed(sorted(selection_model.selectedRows()))]
        # For each row selected
        for i,row in enumerate(selected_row_list):
            # only move the row while it is not the last element, and the row above it is not selected
            # (note that while a row below may have been initially selected, it should by now, be one row lower
            # since we start moving elements of the list upwards starting from the highest index)
            while row < self.channel_model.rowCount()-1 and (row+1) not in selected_row_list:
                # Remove the selected row
                items = self.channel_model.takeRow(row)
                # Add the selected row into a position one above
                self.channel_model.insertRow(row+1,items)
                # Since it is now a newly inserted row, select it again
                selection_model.select(self.channel_model.indexFromItem(items[0]),QItemSelectionModel.SelectCurrent)
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
            check_item = self.channel_model.item(i,CHANNEL_MODEL__CHECKBOX_INDEX)
            channel = check_item.text()
            if channel in self.plot_widgets:
                self.ui.plot_layout.addWidget(self.plot_widgets[channel])
                if check_item.checkState() == Qt.Checked and check_item.isEnabled():
                    self.plot_widgets[channel].show()
                else:
                    self.plot_widgets[channel].hide()
        
class Shot(object):
    def __init__(self, path):
        self.path = path
        
        
        self._traces = {}
        
        # TODO: Get this dynamically
        device_list = ['PulseBlaster', 'NI_PCIe_6363', 'NI_PCI_6733']
        
        # Load connection table
        self.connection_table = ConnectionTable(path)
        
        # store list of channels
        self._channels = {}
        
        # open h5 file
        with h5py.File(path, 'r') as file:
            # Get master pseudoclock
            self.master_pseudoclock_name = file['connection table'].attrs['master_pseudoclock']
            
            # get stop time
            self.stop_time = file['devices/%s'%self.master_pseudoclock_name].attrs['stop_time']
            # self.stop_time = 50
        
            # parse connection table
            self.devices = self.connection_table.find_devices(device_list)
                      
            # Get list of all channels
            for device_name, device_class in self.devices.items():
                device = self.connection_table.find_by_name(device_name)
                # for each child (channel) of this device
                for child_name, child in device.child_list.items():
                    # skip children which are devices themselves
                    if child_name in self.devices:
                        continue
                    # if this child (channel) has it's own children, it is likely a
                    # DDS, so we want it's children, not itself
                    if child.child_list and child.device_class != 'Trigger':
                        for grandchild_name, grandchild in child.child_list.items():
                            self._channels[grandchild_name] = {'device_name':device_name, 'port':'%s_%s'%(child.parent_port, grandchild.parent_port)}
                    # else it has no children, so it is the channel we want
                    else:
                        self._channels[child_name] = {'device_name':device_name, 'port':'%s'%(child.parent_port)}
        
        
        
        
    @property
    def channels(self):
        return self._channels.keys()
    
    def clear_cache(self):
        # clear cache variables to cut down on memory usage
        pass
    
    @property
    def traces(self):
        # if traces cached:
        #    return cached traces and waits
        if self._traces:
            return self._traces
        
        # find master pseudoclock, and build traces for this device
        # get the class of the master pseudoclock
        master_pseudoclock_module = self.devices[self.master_pseudoclock_name]
        # Load the master pseudoclock class
        labscript_devices.import_device(master_pseudoclock_module)
        master_pseudoclock_class = labscript_devices.get_runviewer_class(master_pseudoclock_module)
        master_pseudoclock = master_pseudoclock_class(self.path,self.master_pseudoclock_name)
        master_pseudoclock_traces = master_pseudoclock.get_traces()
        
        for channel, channel_properties in self._channels.items():
            if channel_properties['device_name'] == self.master_pseudoclock_name and channel_properties['port'] in master_pseudoclock_traces:
                self._traces[channel] = master_pseudoclock_traces[channel_properties['port']]
            
        # find children of master pseudoclock which are not Trigger of Pseudoclock devices
        # and build traces for these devices
    
        # for each secondary pseudoclock:
        #    find the trigger trace
        #    build traces for secondary pseudoclock device (and children), offsetting times appropriately by trigger_delay and trigger time
        
        # get list of wait points
                
        # store this built information in cache variables
                
        # return list of traces and wait times
        return self._traces
        
class TempShot(Shot):
    def __init__(self, i):
        Shot.__init__(self, 'shot %d'%i)
        self._channels = ['Bx', 'By', 'Bz', 'Bq']
        
        self.stop_time = i+1
    
        self.traces = {}
        no_x_points = 10000
        for channel in self.channels:
            # self.traces[channel] = (numpy.linspace(0,10,no_x_points), numpy.random.rand(no_x_points))
            x_points = numpy.linspace(0,self.stop_time,no_x_points)
            self.traces[channel] = (x_points, (i+1)*numpy.sin(x_points*numpy.pi+i/11.0*2*numpy.pi))
            
            
    @property
    def channels(self):
        return self._channels
        
    def get_traces(self):
        return self.traces
        
    
if __name__ == "__main__":
    qapplication = QApplication(sys.argv)
    app = RunViewer()
    
    def execute_program():
        qapplication.exec_()
    
    sys.exit(execute_program())

