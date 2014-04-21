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

SHOT_MODEL__CHECKBOX_INDEX = 0
SHOT_MODEL__PATH_INDEX = 1
CHANNEL_MODEL__CHECKBOX_INDEX = 0
CHANNEL_MODEL__CHANNEL_INDEX = 1

class RunViewer(object):
    def __init__(self):
        self.ui = QUiLoader().load(os.path.join(os.path.dirname(os.path.realpath(__file__)),'main.ui'))
        
        #setup shot treeview model
        self.shot_model = QStandardItemModel()
        self.shot_model.setHorizontalHeaderLabels(['','path'])
        self.ui.shot_treeview.setModel(self.shot_model)
        self.shot_model.itemChanged.connect(self.on_shot_selection_changed)
        
        #setup channel treeview model
        self.channel_model = QStandardItemModel()
        self.channel_model.setHorizontalHeaderLabels(['channel'])
        self.ui.channel_treeview.setModel(self.channel_model)
        self.channel_model.itemChanged.connect(self.update_plots)
        
        self.ui.show()
        
        # internal variables
        #self._channels_list = {}
        self.plot_widgets = {}
        self.plot_items = {}
        
        self.temp_load_shots()
    
    def on_shot_selection_changed(self, item):
        self.update_channels_treeview()
    
    def load_shot(self, shot):
        # add shot to shot list
        # Create Items
        items = []
        check_item = QStandardItem()
        check_item.setCheckable(True)
        check_item.setCheckState(Qt.Unchecked) # options are Qt.Checked OR Qt.Unchecked        
        check_item.setData(shot)
        items.append(check_item)
        # script name
        path_item = QStandardItem(shot.path)
        path_item.setEditable(False)
        items.append(path_item)
        self.shot_model.appendRow(items)
        
        self.update_channels_treeview()
    def get_selected_shots(self):
        # get the ticked shots  
        ticked_shots = []
        for i in range(self.shot_model.rowCount()):
            item = self.shot_model.item(i,SHOT_MODEL__CHECKBOX_INDEX)
            if item.checkState() == Qt.Checked:
                ticked_shots.append(item.data())
        return ticked_shots
    
    def update_channels_treeview(self):
        ticked_shots = self.get_selected_shots()
                
        # get set of channels
        channels = {}
        for shot in ticked_shots:
            channels[shot] = set(shot.channels)
        channels_set = frozenset().union(*channels.values())
        
        # now find channels in channels_set which are not in the treeview, and add them
        # now find channels in channels set which are already in the treeview, but deactivated, and activate them
        treeview_channels_dict = {}
        deactivated_treeview_channels_dict = {}
        for i in range(self.channel_model.rowCount()):
            item = self.channel_model.item(i,CHANNEL_MODEL__CHANNEL_INDEX)
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
        ticked_shots = self.get_selected_shots()
        
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
                        if shot not in ticked_shots:
                            self.plot_widgets[channel].removeItem(self.plot_items[channel][shot])
                            to_delete.append(shot)
                    for shot in to_delete:
                        del self.plot_items[channel][shot]
                    
                    # do we need to add any plot items for shots that were not previously selected?
                    for shot in ticked_shots:
                        if shot not in self.plot_items[channel]:
                            plot_item = self.plot_widgets[channel].plot(*shot.traces[channel])
                            self.plot_items[channel][shot] = plot_item
                    
                # If no, create one
                else:
                    self.plot_widgets[channel] = pg.PlotWidget(name=channel)
                    self.plot_widgets[channel].setMinimumHeight(200)
                    self.plot_widgets[channel].setMaximumHeight(200)
                    self.plot_widgets[channel].setLabel('left', channel, units='V')
                    self.plot_widgets[channel].setLabel('bottom', 'Time', units='s')
                    self.plot_widgets[channel].showAxis('right', True)
                    self.ui.plot_layout.addWidget(self.plot_widgets[channel])
                    
                    for shot in ticked_shots:
                        if channel in shot.traces:
                            plot_item = self.plot_widgets[channel].plot(*shot.traces[channel])
                            self.plot_items.setdefault(channel, {})
                            self.plot_items[channel][shot] = plot_item
                
            else:
                if channel in self.plot_widgets:
                    self.plot_widgets[channel].hide()
                
                
                
                
            
        
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
    
        self.traces = {}
        no_x_points = 10000
        for channel in self.channels:
            # self.traces[channel] = (numpy.linspace(0,10,no_x_points), numpy.random.rand(no_x_points))
            x_points = numpy.linspace(0,10,no_x_points)
            self.traces[channel] = (x_points, numpy.sin(x_points*numpy.pi+i/11.0*2*numpy.pi))
            
            
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

