import os,sys
import h5py

from PyQt4 import QtGui, QtCore
import pyqtgraph as pg

from numpy import *

from resample import resample as _resample

def decompose_bitfield(intarray,nbits):
    """converts a single array of unsigned ints into a 2D array
    (len(intarray) x nbits) of ones and zeros"""
    bitarray = zeros((len(intarray),nbits),dtype=int8)
    for i in range(nbits):
        bitarray[:,i] = (intarray & (1 << i)) >> i
    return bitarray

def resample(data_x, data_y, xmin, xmax):
    """This is a function for downsampling the data before plotting
    it. Unlike using nearest neighbour interpolation, this method
    preserves the features of the plot. It chooses what value to use based
    on what values within a region are most different from the values
    it's already chosen. This way, spikes of a short duration won't
    just be skipped over as they would with any sort of interpolation."""
    
    print 'resampling!'
    x_out = float32(linspace(xmin, xmax, 2000))
    y_out = empty(len(x_out), dtype=float32)
    _resample(data_x, data_y, x_out, y_out)
    #y_out = __resample3(data_x, data_y, x_out)
    return x_out, y_out
    
def __resample3(x_in,y_in,x_out):
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
        
def discretise(t,y,stop_time):
    tnew = zeros((len(t),2))
    ynew = zeros((len(y),2))

    tnew[:,0] = t[:]
    tnew[:-1,1] = t[1:]
    tnew= tnew.flatten()
    tnew[-1] = stop_time

    ynew[:,0] = y[:]
    ynew[:,1] = y[:]
    ynew= ynew.flatten()[:]
    return tnew, ynew
    
def open_hdf5_file():
    try:
        assert len(sys.argv) > 1
        hdf5_filename = sys.argv[-1]
    except:
        sys.stderr.write('ERROR: No hdf5 file provided as a command line argument. Stopping.\n')
        sys.exit(1)
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

def parse_connection_table():
    connection_table = hdf5_file['/connection table']
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
        
def get_clock(device_name):
    ancestry = [device_name]
    # Keep going up the family tree til we hit 'None'. The device whose
    # parent is 'None' is the one we're interested in. It's clock is
    # our devices clock.
    while device_name != 'None':
        device_name = parent_lookup[device_name]
        ancestry.append(device_name)
    clocking_device = ancestry[-2]
    clock_type = connection_lookup[ancestry[-3]]
    clock_type = {'fast clock':'FAST_CLOCK','slow_clock':'SLOW_CLOCK'}[clock_type]
    clock_array = hdf5_file['devices'][clocking_device][clock_type]
    print len(clock_array)
    return clock_array
    
def plot_ni_pcie_6363(devicename):
    clock = get_clock(device_name)
    device_group = hdf5_file['devices'][device_name]
    analog_outs = device_group['ANALOG_OUTS']
    digital_outs = device_group['DIGITAL_OUTS']
    #acquisitions = device_group['ACQUISITIONS'] TODO
    analog_channels = device_group.attrs['analog_out_channels']
    analog_channels = [channel.split('/')[1] for channel in analog_channels.split(',')]
    to_plot[devicename+' AO'] = []
    to_plot[devicename+' DO'] = []
    for i, chan in enumerate(analog_channels):
        data = analog_outs[:,i]
        name = name_lookup[devicename, chan]
        #clock, data = discretise(clock,data,clock[-1])
        to_plot[devicename+' AO'].append({'name':name, 'times':array(clock), 'data':array(data, dtype=float32),'device':devicename,'connection':chan})
    digital_bits = decompose_bitfield(digital_outs[:],32)
    for i in range(32):
        connection = (devicename,'port0/line%d'%i)
        if connection in name_lookup:
            data = digital_bits[:,i]
            #clock,data = discretise(clock,data,clock[-1])
            name = name_lookup[connection]
            to_plot[devicename+' DO'].append({'name':name, 'times':array(clock), 'data':array(data, dtype=float32),'device':devicename,'connection':connection[1]})

class MainWindow(QtGui.QMainWindow):
    def __init__(self):
        QtGui.QWidget.__init__(self)
        
        self.setWindowTitle('%s - labscript run viewer'%sys.argv[-1])
        self.setGeometry(QtCore.QRect(0, 0, 800, 800))
        
        central_widget = QtGui.QWidget(self)
        central_layout = QtGui.QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        
        self.tab_widget = QtGui.QTabWidget(self)
        central_layout.addWidget(self.tab_widget)
        self.connect(self.tab_widget, QtCore.SIGNAL('currentChanged(int)'),self.on_tab_changed)
        
        panel_splitter = QtGui.QSplitter(QtCore.Qt.Vertical, self)

        file_scrollarea = QtGui.QScrollArea(self)
        file_scrollarea.setWidgetResizable(True)
        file_scrollarea_contents = QtGui.QWidget(file_scrollarea)
        file_scrollarea.setWidget(file_scrollarea_contents)
        file_scrollarea_contents_layout = QtGui.QVBoxLayout(file_scrollarea_contents)
        file_scrollarea_contents_layout.setContentsMargins(0, 0, 0, 0)
        self.file_list = QtGui.QListWidget(self)
        file_scrollarea_contents_layout.addWidget(self.file_list)
        
        self.global_list = QtGui.QTextEdit(self)
        self.global_list.setFontFamily('mono')
        self.global_list.setLineWrapMode(0)
        self.global_list.setReadOnly(True)
        self.global_list.setText('hello, world!')
        
        panel_splitter.addWidget(file_scrollarea)
        panel_splitter.addWidget(self.global_list)
        
        splitter = QtGui.QSplitter(QtCore.Qt.Horizontal, self)
        splitter.addWidget(panel_splitter)
        splitter.addWidget(central_widget)
        self.setCentralWidget(splitter)
        
        self.plots_by_tab = {}
        self.plots_by_name = {}
        self.tab_names_by_index = {}
        
        self.current_tab_index = 0
        self.plot_all()
        self.resampling_required = True
        self.update_resampling()
        
        
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

        
    def plot_all(self):
        for index, outputclass in enumerate(to_plot):
            tab, layout = self.make_new_tab(outputclass)
            self.plots_by_tab[tab] = []
            self.tab_names_by_index[index] = outputclass
            for i, line in enumerate(to_plot[outputclass]):
                print line['connection']
                if i == 0:
                    pw1 = pw = pg.PlotWidget(name='Plot0',labels={'left':line['name'],'right':line['connection']})
                else:
                    pw = pg.PlotWidget(name='Plot02%d'%i,labels={'left':line['name'],'right':line['connection']})
                    pw.plotItem.setXLink('Plot0')
                pw.plotItem.showScale('right')
                layout.addWidget(pw)
                
                x = line['times']
                y = line['data']
                xnew, ynew = resample(x,y, x[0], x[-1])
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
        for line in to_plot[outputclass]:
            pw = self.plots_by_name[line['name']]
            rect = pw.plotItem.vb.viewRect()
            xmin, xmax = rect.left(), rect.width() + rect.left()
            dx = xmax - xmin
            curve = pw.plotItem.curves[0]
            # We go a bit outside the visible range so that scrolling
            # doesn't immediately go off the edge of the data, and the
            # next resampling might have time to fill in more data before
            # the user sees any empty space.
            xnew, ynew = resample(line['times'],line['data'], xmin-0.2*dx, xmax+0.2*dx)
            curve.updateData(ynew, x=xnew)
                
    def on_tab_changed(self, tabindex):
        newtab = self.tab_widget.widget(tabindex)
        oldtab = self.tab_widget.widget(self.current_tab_index)
        if newtab is not oldtab:
            sourceplot = self.plots_by_tab[oldtab][0]
            targetplot = self.plots_by_tab[newtab][0]
            rect = sourceplot.plotItem.vb.viewRect()
            xmin, xmax = rect.left(), rect.width() + rect.left()
            targetplot.plotItem.setXRange(xmin, xmax,padding=0)
        self.current_tab_index = tabindex
        
if __name__ == '__main__':
    
    if len(sys.argv) == 1:
        sys.argv.append('example.h5')


    plotting_functions = {'ni_pcie_6363':plot_ni_pcie_6363}
    #                      'ni_pci_6733':plot_ni_pci_6733,
    #                      'novatechdds9m':plot_novatechdds9m,
    #                      'pulseblaster':plot_pulseblaster} 
                          

    hdf5_file = open_hdf5_file()
    parent_lookup, connection_lookup, name_lookup = parse_connection_table()
    to_plot = {}
    for device_name in hdf5_file['/devices']:
        device_prefix = '_'.join(device_name.split('_')[:-1])
        if not device_prefix == 'ni_pcie_6363':
            continue
        plotting_functions[device_prefix](device_name)

    app = QtGui.QApplication(sys.argv)
    mainwindow = MainWindow()
    mainwindow.show()
    t = QtCore.QTimer()
    t.timeout.connect(mainwindow.update_resampling)
    t.start(500)
    if sys.flags.interactive != 1:
        sys.exit(app.exec_())


