import os,sys
import h5py
import matplotlib
matplotlib.use('GTKAgg')
from pylab import *
from matplotlib.ticker import MaxNLocator, NullFormatter
from matplotlib.figure import SubplotParams
from matplotlib.backends.backend_gtkagg import FigureCanvasGTKAgg as FigureCanvas
from matplotlib.backends.backend_gtkagg import NavigationToolbar2GTKAgg as NavigationToolbar
import gtk

from resample import resample as _resample

def decompose_bitfield(intarray,nbits):
    """converts a single array of unsigned ints into a 2D array
    (len(intarray) x nbits) of ones and zeros"""
    bitarray = zeros((len(intarray),nbits),dtype=int8)
    for i in range(nbits):
        bitarray[:,i] = (intarray & (1 << i)) >> i
    return bitarray

def resample(data_x, data_y):
    """This is a function for downsampling the data before plotting
    it. Unlike using nearest neighbour interpolation, this method
    preserves the features of the plot. It chooses what value to use based
    on what values within a region are most different from the values
    it's already chosen. This way, spikes of a short duration won't
    just be skipped over as they would with any sort of interpolation."""
    
    print 'resampling!'
    x_out = float32(linspace(x[0]-1, x[-1]+1, 10000))
    y_out = empty(len(x_out), dtype=float32)
    _resample(data_x, data_y, x_out, y_out)
    #y_out = resample3(data_x, data_y, x_out)
    return x_out, y_out
    
def __resample3(x_in,y_in,x_out):
    y_out = empty(len(x_out))
    i = 0
    # Until we get to the data, fill the output array with NaNs (which
    # get ignored when plotted)
    while x_out[i] < x_in[0]:
        y_out[i] = float('NaN')
        i += 1
    # Get the first datapoint:
    y_out[i] = y_in[0]
    i += 1
    j = 1
    # Get values until we get to the end of the data:
    while j < len(x_in):
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
    acquisitions = device_group['ACQUISITIONS']
    analog_channels = device_group.attrs['analog_out_channels']
    analog_channels = [channel.split('/')[1] for channel in analog_channels.split(',')]
    for i, chan in enumerate(analog_channels):
        data = analog_outs[:,i]
        name = name_lookup[devicename, chan]
        #t,y = discretise(clock,data,clock[-1])
        to_plot.append({'name':name, 'times':array(clock), 'data':array(data),'device':devicename,'connection':chan})
    digital_bits = decompose_bitfield(digital_outs[:],32)
    for i in range(32):
        connection = (devicename,'port0/line%d'%i)
        if connection in name_lookup:
            data = digital_bits[:,i]
            #t,y = discretise(clock,data,clock[-1])
            name = name_lookup[connection]
            to_plot.append({'name':name, 'times':array(clock), 'data':array(data),'device':devicename,'connection':connection})

if len(sys.argv) == 1:
    sys.argv.append('example.h5')


plotting_functions = {'ni_pcie_6363':plot_ni_pcie_6363}
#                      'ni_pci_6733':plot_ni_pci_6733,
#                      'novatechdds9m':plot_novatechdds9m,
#                      'pulseblaster':plot_pulseblaster} 
                      

hdf5_file = open_hdf5_file()
parent_lookup, connection_lookup, name_lookup = parse_connection_table()
to_plot = []
for device_name in hdf5_file['/devices']:
    device_prefix = '_'.join(device_name.split('_')[:-1])
    if not device_prefix == 'ni_pcie_6363':
        continue
    plotting_functions[device_prefix](device_name)

params = SubplotParams(hspace=0)
figure(subplotpars = params)
axes = []
to_plot *= 5
for i, line in enumerate(to_plot):
    if i == 0:
        ax1 = ax = subplot(len(to_plot),1,i+1)
    else:
        ax = subplot(len(to_plot),1,i+1,sharex=ax1)
    x = array(line['times'])
    y = array(line['data'])
    if y.dtype == int32:
        y = float32(y)
    xnew, ynew = resample(x,y)
    mn,mx = min(y), max(y)
    gca().set_ylim(mn - 0.1 *(mx - mn), mx + 0.1 *(mx - mn))
    gca().set_xlim(min(xnew), max(xnew))
    plot(xnew, ynew)
    
    gca().yaxis.set_major_locator(MaxNLocator(steps=[1,2,3,4,5,6,7,8,9,10], prune = 'both'))
    axes.append(gca())
    if i < len(to_plot)-1:
        gca().tick_params(direction='in',labelsize='small', labelbottom='off')
    else:
        xlabel('Time (seconds)')
        gca().tick_params(direction='in',labelsize='small')
    ylabel(line['name'])

    #grid(True)

win = gtk.Window()
win.connect("destroy", gtk.main_quit)
win.set_default_size(400,300)
win.set_title("Labscript experiment preview")

vbox=gtk.VBox()
win.add(vbox)
#canvas = FigureCanvas(gcf())  # a gtk.DrawingArea
canvas =gcf().canvas
canvas.parent.remove(canvas)
vbox.pack_start(canvas)
toolbar = NavigationToolbar(canvas, win)

vbox.pack_start(toolbar,False,False)


dy = 1
dx = 1

class Callbacks:
    def onscroll(self, event):
        #print event.button, event.key, event.button, event.step, event.inaxes
        if event.key == 'control' and event.inaxes:
            xmin, xmax, ymin, ymax = event.inaxes.axis()
            event.inaxes.set_ylim(ymin + event.step*dy, ymax + event.step*dy)
        else:
            xmin, xmax, ymin, ymax = ax1.axis()
            ax1.set_xlim(xmin + event.step*dy, xmax + event.step*dx)
        canvas.draw_idle()


callbacks = Callbacks()
canvas.mpl_connect('scroll_event',callbacks.onscroll)
win.show_all()

gtk.main()



