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
        
        self.ui.show()
        
        # internal variables
        #self._channels_list = {}
        self.plot_widgets = {}
        self.plot_items = {}
        
        self.temp_load_shots()
    
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
                    self.ui.plot_layout.addWidget(self.plot_widgets[channel])
                    
                    for shot, colour in ticked_shots.items():
                        if channel in shot.traces:
                            plot_item = self.plot_widgets[channel].plot(shot.traces[channel][0], shot.traces[channel][1], pen=pg.mkPen(QColor(colour), width=2))
                            self.plot_items.setdefault(channel, {})
                            self.plot_items[channel][shot] = plot_item
                
            else:
                if channel in self.plot_widgets:
                    self.plot_widgets[channel].hide()
                
    def on_x_axis_reset(self):
        self._hidden_plot[0].enableAutoRange(axis=pg.ViewBox.XAxis)   
        
    def on_y_axes_reset(self):
        for plot_widget in self.plot_widgets.values():
            plot_widget.enableAutoRange(axis=pg.ViewBox.YAxis)
           
    def temp_load_shots(self):
        for i in range(10):
            shot = TempShot(i)
            self.load_shot(shot)
            
        
class Shot(object):
    def __init__(self, path):
        self.path = path
        
    def get_traces(self):
        pass
        
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

