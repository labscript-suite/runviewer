import os,sys
import h5py

from PyQt4 import QtGui, QtCore
import pyqtgraph as pg

from numpy import *

from resample import resample as _resample

# This provides debug info without having to run from a terminal, and
# avoids a stupid crash on Windows when there is no command window:
if not sys.stdout.isatty():
    sys.stdout = sys.stderr = open('debug.log','w',1)
    
class FileAndDataOps(object):

    def __init__(self):
        self.plotting_functions = {'ni_pcie_6363':self.plot_ni_pcie_6363,
                                   'ni_pci_6733':self.plot_ni_pci_6733,
                                  'novatechdds9m':self.plot_novatechdds9m,
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

    def resample(self,data_x, data_y, xmin, xmax, stop_time):
        """This is a function for downsampling the data before plotting
        it. Unlike using nearest neighbour interpolation, this method
        preserves the features of the plot. It chooses what value to
        use based on what values within a region are most different
        from the values it's already chosen. This way, spikes of a short
        duration won't just be skipped over as they would with any sort
        of interpolation."""
        x_out = float32(linspace(xmin, xmax, 2000))
        y_out = empty(len(x_out), dtype=float32)
        _resample(data_x, data_y, x_out, y_out,float32(stop_time))
        #y_out = self.__resample3(data_x, data_y, x_out,float32(stop_time))
        return x_out, y_out
        
    def __resample3(self,x_in,y_in,x_out, stop_time):
        """This is a Python implementation of the C extension. For
        debugging and developing the C extension."""
        y_out = empty(len(x_out))
        i = 0
        j = 1
        # A couple of special cases that I don't want to have to put extra checks in for:
        if x_out[-1] < x_in[0] or x_out[0] > stop_time:
            # We're all the way to the left of the data or all the way to the right. Fill with NaNs:
            while i < len(x_out):
                y_out[i] = float('NaN')
                i += 1
        elif x_out[0] > x_in[-1]:
            # We're after the final clock tick, but before stop_time
            while i < len(x_out):
                if x_out[i] < stop_time:
                    y_out[i] = y_in[-1]
                else:
                    y_out[i] = float('NaN')
                i += 1
        else:
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
            # Fill the remainder of the array with the last datapoint,
            # if t < stop_time, and then NaNs after that:
            while i < len(x_out):
                if x_out[i] < stop_time:
                    y_out[i] = y_in[-1]
                else:
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
        connection_dict = [(line['name'],line['parent port']) for line in connection_table]
        # For looking up the name of a device if you know its parent and connection:
        name_dict = [((line['parent'],line['parent port']),line['name']) for line in connection_table]
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
        stop_time = self.hdf5_file['devices'][clocking_device].attrs['stop_time']
        return stop_time, array(clock_array)
        
    def plot_ni_card(self, device_name, n_digitals):
        stop_time, clock = self.get_clock(device_name)
        device_group = self.hdf5_file['devices'][device_name]
        try:
            analog_outs = device_group['ANALOG_OUTS']
        except:
            analog_outs = None
        try:
            digital_outs = device_group['DIGITAL_OUTS']
        except:
            digital_outs = None
        try:
            acquisitions = device_group['ACQUISITIONS']
        except:
            acquisitions = None
        if analog_outs is not None:
            analog_channels = device_group.attrs['analog_out_channels']
            analog_channels = [channel.split('/')[1] for channel in analog_channels.split(',')]
       
        self.to_plot[device_name+' AO'] = []
        self.to_plot[device_name+' AI'] = []
        self.to_plot[device_name+' DO'] = []
        if analog_outs is not None:
            for i, chan in enumerate(analog_channels):
                data = analog_outs[:,i]
                name = self.name_lookup[device_name, chan]
                self.to_plot[device_name+' AO'].append({'name':name, 'times':clock, 'data':array(data, dtype=float32),
                                                        'device':device_name,'connection':chan,'stop_time':stop_time})
        if digital_outs is not None:
            digital_bits = self.decompose_bitfield(digital_outs[:],n_digitals)
            for i in range(32):
                connection = (device_name,'port0/line%d'%i)
                if connection in self.name_lookup:
                    data = digital_bits[:,i]
                    name = self.name_lookup[connection]
                    self.to_plot[device_name+' DO'].append({'name':name, 'times':clock, 'data':array(data, dtype=float32),
                                                            'device':device_name,'connection':connection[1], 'stop_time':stop_time})
        if acquisitions is not None:
            input_chans = {}
            for i, acquisition in enumerate(acquisitions):
                chan = acquisition['connection']
                if chan not in input_chans:
                    input_chans[chan] = []
                input_chans[chan].append(acquisition)
            for chan in input_chans:
                name = self.name_lookup[device_name, chan]
                times = []
                gate = []
                labels = {} # For putting text on the plot at specified x points
                for acquisition in input_chans[chan]:
                    start = acquisition['start']
                    stop = acquisition['stop']
                    labels[start] = acquisition['label']
                    # A square pulse:
                    times.extend(2*[start])
                    times.extend(2*[stop])
                    gate.extend([0,1,1,0])
                if not 0 in times:
                    times.insert(0,0)
                    gate.insert(0,0)
                if not clock[-1] in times:
                    times.append(clock[-1])
                    gate.append(0)
            self.to_plot[device_name+' AI'].append({'name':name, 'times':array(times, dtype=float32), 
                                                    'data':array(gate, dtype=float32),'device':device_name,
                                                    'connection':chan,'labels':labels, 'stop_time':stop_time})
        
        if len(self.to_plot[device_name+' AO']) == 0:
            del self.to_plot[device_name+' AO']
        if len(self.to_plot[device_name+' DO']) == 0:
            del self.to_plot[device_name+' DO']
        if len(self.to_plot[device_name+' AI']) == 0:
            del self.to_plot[device_name+' AI']
            
    def plot_ni_pcie_6363(self, device_name):
        self.plot_ni_card(device_name,32)
    
    def plot_ni_pci_6733(self, device_name):
        self.plot_ni_card(device_name, 0)
                           
    def plot_pulseblaster(self,device_name):
        stop_time, clock = self.get_clock(device_name)
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
                self.to_plot[device_name+' flags'].append({'name':name, 'times':clock, 'data':array(data, dtype=float32),
                                                           'device':device_name,'connection':connection[1], 'stop_time':stop_time})
        self.to_plot[device_name+' DDS'] = []
        for i in range(2):
            connection = (device_name, 'dds %d'%i)
            if connection in self.name_lookup:
                print 'success!'
                name = self.name_lookup[connection]
                freqtable = device_group['DDS%d'%i]['FREQ_REGS']
                amptable = device_group['DDS%d'%i]['AMP_REGS']
                phasetable = device_group['DDS%d'%i]['PHASE_REGS']
                freqregs = states['freq%d'%i]
                ampregs = states['amp%d'%i]
                phaseregs = states['phase%d'%i]
                freqs = array(freqtable)[freqregs]
                amps = array(amptable)[ampregs]
                phases = array(phasetable)[phaseregs]
                self.to_plot[device_name+' DDS'].append({'name':name + ' (freq)', 'times':clock,
                                                         'data':array(freqs, dtype=float32),'device':device_name,
                                                         'connection':connection[1], 'stop_time':stop_time})
                self.to_plot[device_name+' DDS'].append({'name':name + ' (amp)', 'times':clock,
                                                         'data':array(amps, dtype=float32),'device':device_name,
                                                         'connection':connection[1], 'stop_time':stop_time})
                self.to_plot[device_name+' DDS'].append({'name':name + ' (phase)', 'times':clock,
                                                         'data':array(phases, dtype=float32),'device':device_name,
                                                         'connection':connection[1], 'stop_time':stop_time})
        if len(self.to_plot[device_name+' DDS']) == 0:
            del self.to_plot[device_name+' DDS']
                
                
    def plot_novatechdds9m(self, device_name):
        stop_time, clock = self.get_clock(device_name)
        device_group = self.hdf5_file['devices'][device_name]
        try:
            table_data = device_group['TABLE_DATA']
        except:
            table_data = None
        try:
            static_data = device_group['STATIC_DATA']
        except:
            static_data = None
        self.to_plot[device_name] = []
        if table_data is not None:
            for i in range(2):
                connection = (device_name, 'channel %d'%i)
                if connection in self.name_lookup:
                    name = self.name_lookup[connection]
                    freqs = table_data['freq%d'%i]
                    amps = table_data['amp%d'%i]
                    phases = table_data['phase%d'%i]
                    self.to_plot[device_name].append({'name':name + ' (freq)', 'times':clock,'data':array(freqs, dtype=float32),
                                                      'device':device_name,'connection':connection[1], 'stop_time':stop_time})
                    self.to_plot[device_name].append({'name':name + ' (amp)', 'times':clock,'data':array(amps, dtype=float32),
                                                      'device':device_name,'connection':connection[1], 'stop_time':stop_time})
                    self.to_plot[device_name].append({'name':name + ' (phase)', 'times':clock, 'data':array(phases, dtype=float32),
                                                      'device':device_name,'connection':connection[1], 'stop_time':stop_time})
        if static_data is not None:
            for i in [2,3]:
                connection = (device_name, 'channel %d'%i)
                if connection in self.name_lookup:
                    name = self.name_lookup[connection]
                    freqs = zeros(len(clock)) + static_data['freq%d'%i][0]
                    amps = zeros(len(clock)) + static_data['amp%d'%i][0]
                    phases = zeros(len(clock)) + static_data['phase%d'%i][0]
                    self.to_plot[device_name].append({'name':name + ' (freq)', 'times':clock,'data':array(freqs, dtype=float32),
                                                      'device':device_name,'connection':connection[1], 'stop_time':stop_time})
                    self.to_plot[device_name].append({'name':name + ' (amp)', 'times':clock,'data':array(amps, dtype=float32),
                                                      'device':device_name,'connection':connection[1], 'stop_time':stop_time})
                    self.to_plot[device_name].append({'name':name + ' (phase)', 'times':clock, 'data':array(phases, dtype=float32),
                                                      'device':device_name,'connection':connection[1], 'stop_time':stop_time})
        
        if len(self.to_plot[device_name]) == 0:
            del self.to_plot[device_name]
        
                
        
class MainWindow(QtGui.QMainWindow):
    def __init__(self, data_ops, startfolder, startfile):
        QtGui.QWidget.__init__(self)
        self.data_ops = data_ops
        self.setGeometry(QtCore.QRect(20, 40, 1000, 800))
        
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
        
        self.progress = QtGui.QProgressBar(self)
        central_layout.addWidget(self.progress)
        self.progress.hide()
        self.plots_by_name = {}
        self.file_list.setFocus()
        self.show()
        self.load_file_list(startfolder, startfile)        
        self.t = QtCore.QTimer()
        self.t.timeout.connect(self.update_resampling)
        self.resampling_required = False
        self.t.start(500)
    
    def load_file_list(self, folder, filename):
        self.folder = folder
        h5_files = [name for name in os.listdir(folder) if name.endswith('.h5')]
        self.file_list.insertItems(0, sorted(h5_files))
        if filename is None:
            self.file_list.setCurrentItem(self.file_list.item(0))
        else:
            fileitem =  self.file_list.findItems(filename,QtCore.Qt.MatchFlags(1))[0]
            self.file_list.setCurrentItem(fileitem)
             
    def on_file_selection_changed(self,item):
        self.plots_by_tab = {}
        for pw in self.plots_by_name.values():
            pw.close()
        self.plots_by_name = {}
        self.tab_names_by_index = {}
        
        self.loading_new_file = True
        self.current_tab_index = 0
        self.tab_widget.clear()
        self.resampling_required = False
        fname = os.path.join(self.folder,str(item.text()))
        self.setWindowTitle('%s - labscript run viewer'%fname)
        self.file_list.setItemSelected(item,True)
        self.progress.show()
        self.tab_widget.hide()
        try:
            self.plot_all(fname)
        except:
            raise
        finally:
            self.tab_widget.show()
            self.progress.close()
            self.loading_new_file = False
            
    def make_new_tab(self,text):      

        tab = QtGui.QWidget(self)
        tab_layout = QtGui.QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        scrollArea = QtGui.QScrollArea(self)
        scrollArea.setWidgetResizable(True)
        scrollArea.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)


        scrollAreaWidgetContents = QtGui.QWidget(self)
        
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
        self.progress.setMaximum(sum([len(to_plot[outputclass]) for outputclass in to_plot]))
        progress_index = 0
        for index, outputclass in enumerate(sorted(to_plot)):
            tab, layout = self.make_new_tab(outputclass)
            self.plots_by_tab[tab] = []
            self.tab_names_by_index[index] = outputclass
            for i, line in enumerate(to_plot[outputclass]):
                self.progress.setValue(progress_index)
                progress_index += 1
                if i == 0:
                    pw1 = pw = pg.PlotWidget(name='Plot0',labels={'left':line['name'],'right':line['connection']})
                else:
                    pw = pg.PlotWidget(name='Plot%d'%i,labels={'left':line['name'],'right':line['connection']})
                    pw.plotItem.setXLink('Plot0')
                pw.plotItem.showScale('right')
                #pw.plotItem.showScale('bottom',False)
                layout.addWidget(pw)
                if 'labels' in line:
                    for x in line['labels']:
                        textitem = QtGui.QGraphicsTextItem(line['labels'][x])
                        pw.plotItem.addItem(textitem)
                        textitem.setPos(x,0)
                        textitem.setFont(QtGui.QFont('mono', 11))
                        textitem.rotate(-90)
                        textitem.setDefaultTextColor(QtGui.QColor('white')) 
                        textitem.setFlag(textitem.ItemIgnoresTransformations)
                        textitem.show()
                        
                x = line['times']
                y = line['data']
                assert len(x) == len(y), '%d %d %s'%(len(x), len(y), outputclass)
                xnew, ynew = data_ops.resample(x, y, x[0], line['stop_time'], line['stop_time'])
                plot = pw.plot(y=ynew,x=xnew)
                pw.plotItem.setManualXScale()
                pw.plotItem.setXRange(x[0], line['stop_time'], padding=0)
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
        self.reset_x()     
    
    def on_xrange_changed(self, *args):
        # Resampling only happens every 500ms, if required. We don't
        # need to call it every time the xrange is changed, that's a
        # waste of cpu cycles and slows things down majorly.
        self.resampling_required = True
    
    def reset_x(self,*args):
        outputclass = self.tab_names_by_index[self.current_tab_index]
        for line in data_ops.to_plot[outputclass]:
            pw = self.plots_by_name[line['name']]
            x = line['times']
            pw.plotItem.setXRange(x[0], line['stop_time'],padding=0)
            
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
            xnew, ynew = data_ops.resample(line['times'],line['data'], xmin-0.2*dx, xmax+0.2*dx, line['stop_time'])
            curve.updateData(ynew, x=xnew)
                
    def on_tab_changed(self, tabindex):
        if self.loading_new_file:
            # ignore the tab changes due to tab creation and destruction:
            return
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
    
    if len(sys.argv) > 1:
        arg =  sys.argv[1]
        if os.path.isdir(arg):
            startfolder = arg
            startfile = None
        elif os.path.exists(arg):
            startfolder, startfile = os.path.split(os.path.abspath(arg))
        elif os.path.exists(os.path.split(arg)[0]):
            startfolder, startfile = os.path.abspath(os.path.split(arg)[0]), None
        else:
            startfolder, startfile = os.getcwd(), None
    else:
        startfolder = os.getcwd()
        startfile = None
        
    data_ops = FileAndDataOps()
    app = QtGui.QApplication(sys.argv)
    gui = MainWindow(data_ops, startfolder, startfile)
    
    if sys.flags.interactive != 1:
        sys.exit(app.exec_())


