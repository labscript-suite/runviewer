import os,sys
import h5py

from PyQt4 import QtGui, QtCore
import pyqtgraph as pg

from numpy import *

from resample import resample as _resample

class FileAndDataOps(object):

    def __init__(self):
        self.plotting_functions = {'ni_pcie_6363':self.plot_ni_pcie_6363,
                                  #'ni_pci_6733':plot_ni_pci_6733,
                                  #'novatechdds9m':plot_novatechdds9m,
                                  'pulseblaster':self.plot_pulseblaster} 

    def get_data(self, h5_filename=None):
        self.hdf5_file = self.open_hdf5_file(h5_filename)
        if not self.hdf5_file:
            return {}
        self.parent_lookup, self.connection_lookup, self.name_lookup = self.parse_connection_table()
        globals_and_info = self.get_globals_and_info(self.hdf5_file)
        self.to_plot = {}
        for device_name in self.hdf5_file['/devices']:
            device_prefix = '_'.join(device_name.split('_')[:-1])
            if not device_prefix in self.plotting_functions:
                print 'device %s not supported yet'%device_prefix
                continue
            self.plotting_functions[device_prefix](device_name)
        return self.to_plot, globals_and_info
    
    def get_globals_and_info(self,hdf5_file):
        globalvars = []
        for name, val in hdf5_file['globals'].attrs.items():
            globalvars.append('%s = %s'%(name,str(val)))
        globalsstring = '\n'.join(globalvars)
        return globalsstring
        
    def decompose_bitfield(self,intarray,nbits):
        """converts a single array of unsigned ints into a 2D array
        (len(intarray) x nbits) of ones and zeros"""
        bitarray = zeros((len(intarray),nbits),dtype=int8)
        for i in range(nbits):
            bitarray[:,i] = (intarray & (1 << i)) >> i
        return bitarray

    def resample(self,data_x, data_y, xmin, xmax):
        """This is a function for downsampling the data before plotting
        it. Unlike using nearest neighbour interpolation, this method
        preserves the features of the plot. It chooses what value to use based
        on what values within a region are most different from the values
        it's already chosen. This way, spikes of a short duration won't
        just be skipped over as they would with any sort of interpolation."""
        
        x_out = float32(linspace(xmin, xmax, 2000))
        y_out = empty(len(x_out), dtype=float32)
        _resample(data_x, data_y, x_out, y_out)
        #y_out = __resample3(data_x, data_y, x_out)
        return x_out, y_out
        
    def __resample3(self,x_in,y_in,x_out):
        y_out = empty(len(x_out))
        i = 0
        j = 1
        # Until we get to the data, fill the output array with NaNs (which
        # get ignored when plotted)
        while x_out[i] < x_in[0]:
            y_out[i] = float('NaN')
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
                if abs(y_in[j] - y_out[i-1]) > abs(y_out[i] - y_out[i-1]):
                    # If so, use this source value:
                    y_out[i] = y_in[j]
                j+=1
            i += 1
        # Get the last datapoint:
        if i < len(x_out):
            y_out[i] = y_in[-1]
            i += 1
        # Fill the remainder of the array with NaNs:
        while i < len(x_out):
            y_out[i] = float('NaN')
            i += 1
        return y_out
        
    def open_hdf5_file(self,hdf5_filename=None):
        if not hdf5_filename:
            try:
                assert len(sys.argv) > 1
                hdf5_filename = sys.argv[-1]
            except:
                return
                sys.stderr.write('ERROR: No hdf5 file provided as a command line argument. Stopping.\n')
        if not os.path.exists(hdf5_filename):
            sys.stderr.write('ERROR: Provided hdf5 filename %s doesn\'t exist. Stopping.\n'%hdf5_filename)
            sys.exit(1)
        try:
            hdf5_file = h5py.File(hdf5_filename)
        except:
            sys.stderr.write('ERROR: Couldn\'t open %s for reading. '%hdf5_filename +
                             'Check it is a valid hdf5 file.\n')
            sys.exit(1) 
        return hdf5_file

    def parse_connection_table(self):
        connection_table = self.hdf5_file['/connection table']
        # For looking up the parent of a device if you know its name:
        parent_dict = [(line['name'],line['parent']) for line in connection_table]
        # For looking up the connection of a device if you know its name:
        connection_dict = [(line['name'],line['connected to']) for line in connection_table]
        # For looking up the name of a device if you know its parent and connection:
        name_dict = [((line['parent'],line['connected to']),line['name']) for line in connection_table]
        parent_dict = dict(parent_dict)
        connection_dict = dict(connection_dict)
        name_dict = dict(name_dict)
        return parent_dict, connection_dict, name_dict
            
    def get_clock(self,device_name):
        ancestry = [device_name]
        # Keep going up the family tree til we hit 'None'. The device whose
        # parent is 'None' is the one we're interested in. It's clock is
        # our devices clock.
        while device_name != 'None':
            device_name = self.parent_lookup[device_name]
            ancestry.append(device_name)
        clocking_device = ancestry[-2]
        try:
            clock_type = self.connection_lookup[ancestry[-3]]
        except IndexError:
            # Must be a pulseblaster:
            clock_type = 'slow clock'   
        clock_type = {'fast clock':'FAST_CLOCK','slow clock':'SLOW_CLOCK'}[clock_type]
        clock_array = self.hdf5_file['devices'][clocking_device][clock_type]
        return clock_array
        
    def plot_ni_pcie_6363(self, device_name):
        clock = array(self.get_clock(device_name))
        device_group = self.hdf5_file['devices'][device_name]
        analog_outs = device_group['ANALOG_OUTS']
        digital_outs = device_group['DIGITAL_OUTS']
        #acquisitions = device_group['ACQUISITIONS'] TODO
        analog_channels = device_group.attrs['analog_out_channels']
        analog_channels = [channel.split('/')[1] for channel in analog_channels.split(',')]
        self.to_plot[device_name+' AO'] = []
        self.to_plot[device_name+' DO'] = []
        for i, chan in enumerate(analog_channels):
            data = analog_outs[:,i]
            name = self.name_lookup[device_name, chan]
            self.to_plot[device_name+' AO'].append({'name':name, 'times':clock, 'data':array(data, dtype=float32),'device':device_name,'connection':chan})
        digital_bits = self.decompose_bitfield(digital_outs[:],32)
        for i in range(32):
            connection = (device_name,'port0/line%d'%i)
            if connection in self.name_lookup:
                data = digital_bits[:,i]
                name = self.name_lookup[connection]
                self.to_plot[device_name+' DO'].append({'name':name, 'times':clock, 'data':array(data, dtype=float32),'device':device_name,'connection':connection[1]})

    def plot_pulseblaster(self,device_name):
        pb_inst_by_name = {'CONTINUE':0,'STOP': 1, 'LOOP': 2, 'END_LOOP': 3,'BRANCH': 6, 'WAIT': 8}
        pb_inst_by_number = dict((v,k) for k,v in pb_inst_by_name.iteritems())
        clock = array(self.get_clock(device_name))
        device_group = self.hdf5_file['devices'][device_name]
        pulse_program = device_group['PULSE_PROGRAM']
        clock_indices = device_group['CLOCK_INDICES']
        flags = empty(len(clock), dtype = uint32)
        states = pulse_program[clock_indices]
        flags = states['flags']
        flags = self.decompose_bitfield(flags, 12)
        self.to_plot[device_name+' flags'] = []
        for i in range(12):
            connection = (device_name, 'flag %d'%i)
            if connection in self.name_lookup:
                name = self.name_lookup[connection]
                data = flags[:,i]
                self.to_plot[device_name+' flags'].append({'name':name, 'times':clock, 'data':array(data, dtype=float32),'device':device_name,'connection':connection[1]})
                
class MainWindow(QtGui.QMainWindow):
    def __init__(self, data_ops):
        QtGui.QWidget.__init__(self)
        self.data_ops = data_ops
        self.setGeometry(QtCore.QRect(0, 0, 1000, 800))
        
        central_widget = QtGui.QWidget(self)
        central_layout = QtGui.QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        
        self.tab_widget = QtGui.QTabWidget(self)
        central_layout.addWidget(self.tab_widget)
        self.connect(self.tab_widget, QtCore.SIGNAL('currentChanged(int)'),self.on_tab_changed)
        
        panel_splitter = QtGui.QSplitter(QtCore.Qt.Vertical, self)
        panel_splitter.setHandleWidth(1)

        file_scrollarea = QtGui.QScrollArea(self)
        file_scrollarea.setWidgetResizable(True)
        file_scrollarea_contents = QtGui.QWidget(file_scrollarea)
        file_scrollarea.setWidget(file_scrollarea_contents)
        file_scrollarea_contents_layout = QtGui.QVBoxLayout(file_scrollarea_contents)
        file_scrollarea_contents_layout.setContentsMargins(0, 0, 0, 0)
        self.file_list = QtGui.QListWidget(self)
        self.file_list.currentItemChanged.connect(self.on_file_selection_changed)
        file_scrollarea_contents_layout.addWidget(self.file_list)
        
        self.global_list = QtGui.QTextEdit(self)
        self.global_list.setFontFamily('mono')
        self.global_list.setLineWrapMode(0)
        self.global_list.setReadOnly(True)
        self.global_list.setText('No file opened.')
        
        panel_splitter.addWidget(file_scrollarea)
        panel_splitter.addWidget(self.global_list)
        
        splitter = QtGui.QSplitter(QtCore.Qt.Horizontal, self)
        splitter.setHandleWidth(1)
        splitter.addWidget(panel_splitter)
        splitter.addWidget(central_widget)
        splitter.setSizes ([200,800])
        self.setCentralWidget(splitter)
        
        self.load_file_list(os.getcwd())        
        
        self.show()
        self.t = QtCore.QTimer()
        self.t.timeout.connect(self.update_resampling)
        self.resampling_required = False
        self.t.start(500)
    
    def load_file_list(self, folder):
        self.folder = folder
        h5_files = [name for name in os.listdir(folder) if name.endswith('.h5')]
        self.file_list.insertItems(0, sorted(h5_files))
        self.file_list.setCurrentItem(self.file_list.item(0))
        
    def on_file_selection_changed(self,item):
        self.plots_by_tab = {}
        self.plots_by_name = {}
        self.tab_names_by_index = {}
        
        self.current_tab_index = 0
        self.tab_widget.clear()
        self.resampling_required = False
        fname = os.path.join(self.folder,str(item.text()))
        self.setWindowTitle('%s - labscript run viewer'%fname)
        self.plot_all(fname)
                
    def make_new_tab(self,text):      

        tab = QtGui.QWidget(self)
        tab_layout = QtGui.QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        scrollArea = QtGui.QScrollArea(self)
        scrollArea.setWidgetResizable(True)
        scrollArea.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)


        scrollAreaWidgetContents = QtGui.QWidget(scrollArea)


        scrollArea.setWidget(scrollAreaWidgetContents)
        scrollarea_layout = QtGui.QVBoxLayout(scrollAreaWidgetContents)
        scrollarea_layout.setContentsMargins(0, 0, 0, 0)
        scrollarea_layout.setSpacing(0)
        
        tab_layout.addWidget(scrollArea)
        self.tab_widget.addTab(tab,text)
        
        return tab, scrollarea_layout

        
    def plot_all(self, h5_filename=None):
        to_plot, info_string = data_ops.get_data(h5_filename)
        self.global_list.setText(info_string)
        for index, outputclass in enumerate(to_plot):
            tab, layout = self.make_new_tab(outputclass)
            self.plots_by_tab[tab] = []
            self.tab_names_by_index[index] = outputclass
            for i, line in enumerate(to_plot[outputclass]):
                if i == 0:
                    pw1 = pw = pg.PlotWidget(name='Plot0',labels={'left':line['name'],'right':line['connection']})
                else:
                    pw = pg.PlotWidget(name='Plot02%d'%i,labels={'left':line['name'],'right':line['connection']})
                    pw.plotItem.setXLink('Plot0')
                pw.plotItem.showScale('right')
                layout.addWidget(pw)
                
                x = line['times']
                y = line['data']
                xnew, ynew = data_ops.resample(x,y, x[0], x[-1])
                plot = pw.plot(y=ynew,x=xnew)
                pw.plotItem.setManualXScale()
                pw.plotItem.setXRange(x[0], x[-1],padding=0)
                pw.plotItem.setManualYScale()
                ymin = min(ynew)
                ymax = max(ynew)
                dy = ymax - ymin
                pw.plotItem.setYRange(ymin - 0.1*dy, ymax + 0.1*dy)
                self.plots_by_tab[tab].append(pw)
                self.plots_by_name[line['name']] = pw
                pw.setMinimumHeight(200)
                pw.setMaximumHeight(200)
            pw1.plotItem.sigXRangeChanged.connect(self.on_xrange_changed)
            layout.addStretch()
    
    def on_xrange_changed(self, *args):
        # Resampling only happens every 500ms, if required. We don't
        # need to call it every time the xrange is changed, that's a
        # waste of cpu cycles and slows things down majorly.
        self.resampling_required = True
        
    def update_resampling(self):
        if not self.resampling_required:
            return
        self.resampling_required = False
        outputclass = self.tab_names_by_index[self.current_tab_index]
        for line in data_ops.to_plot[outputclass]:
            pw = self.plots_by_name[line['name']]
            rect = pw.plotItem.vb.viewRect()
            xmin, xmax = rect.left(), rect.width() + rect.left()
            dx = xmax - xmin
            curve = pw.plotItem.curves[0]
            # We go a bit outside the visible range so that scrolling
            # doesn't immediately go off the edge of the data, and the
            # next resampling might have time to fill in more data before
            # the user sees any empty space.
            xnew, ynew = data_ops.resample(line['times'],line['data'], xmin-0.2*dx, xmax+0.2*dx)
            curve.updateData(ynew, x=xnew)
                
    def on_tab_changed(self, tabindex):
        newtab = self.tab_widget.widget(tabindex)
        oldtab = self.tab_widget.widget(self.current_tab_index)
        if oldtab and (newtab is not oldtab):
            sourceplot = self.plots_by_tab[oldtab][0]
            targetplot = self.plots_by_tab[newtab][0]
            rect = sourceplot.plotItem.vb.viewRect()
            xmin, xmax = rect.left(), rect.width() + rect.left()
            targetplot.plotItem.setXRange(xmin, xmax,padding=0)
        self.current_tab_index = tabindex
        
if __name__ == '__main__':
    
#    if len(sys.argv) == 1:
#        sys.argv.append('example.h5')
    
    data_ops = FileAndDataOps()
    app = QtGui.QApplication(sys.argv)
    gui = MainWindow(data_ops)
    
    if sys.flags.interactive != 1:
        sys.exit(app.exec_())


