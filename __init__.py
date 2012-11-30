import numpy
from numpy import array

import h5_lock, h5py
import traces
import extraction_functions
from resample import resample as _resample

labscript_auto_init = False
import labscript

def resample(data_x, data_y, xmin, xmax, npts=2000, stop_time=None):
        """This is a function for downsampling the data before plotting
        it. Unlike using nearest neighbour interpolation, this method
        preserves the features of the plot. It chooses what value to
        use based on what values within a region are most different
        from the values it's already chosen. This way, spikes of a short
        duration won't just be skipped over as they would with any sort
        of interpolation."""
        if stop_time is None:
            stop_time = xmax
        x_out = numpy.linspace(xmin, xmax, npts)
        y_out = numpy.empty(len(x_out))
        # convert to 64 bit floats:
        data_x = array(data_x,dtype=float)
        data_y = array(data_y, dtype=float)
        _resample(data_x, data_y, x_out, y_out,float(stop_time))
        return x_out, y_out
               
class Shot(object):
    """A class representing all the output instructions in a single shot"""
    def __init__(self, path):
        with h5py.File(path,'r') as h5_file:
            self.parse_connection_table(h5_file)
            self.traces = []
            for device_name in h5_file['/devices']:
                device_class = self.class_lookup[device_name]
                try:
                    extraction_function = getattr(extraction_functions, device_class)
                except AttributeError:
                    raise NotImplementedError('device %s not supported'%device_class)
                clock = self.get_clock(h5_file, device_name)
                traces = extraction_function(h5_file, device_name, clock, self.name_lookup)
                self.traces.extend(traces)
        
    def parse_connection_table(self, h5_file):
        connection_table = h5_file['/connection table']
        # For looking up the parent of a device if you know its name:
        parent_dict = [(line['name'],line['parent']) for line in connection_table]
        # For looking up the connection of a device if you know its name:
        connection_dict = [(line['name'],line['parent port']) for line in connection_table]
        # For looking up the name of a device if you know its parent and connection:
        name_dict = [((line['parent'],line['parent port']),line['name']) for line in connection_table]
        # For looking up the class of a device if you know its name:
        class_dict = [(line['name'],line['class']) for line in connection_table]
        
        self.parent_lookup = dict(parent_dict)
        self.connection_lookup = dict(connection_dict)
        self.name_lookup = dict(name_dict)
        self.class_lookup = dict(class_dict)

    def get_clock(self, h5_file, device_name):
        device_class = getattr(labscript, self.class_lookup[device_name])
        if issubclass(device_class, labscript.PseudoClock):
            # The device is a pseudoclock. Its data extraction function
            # will be responsible for extracting its own clock.
            return None
        # Traverse the family tree upward until we find a pseudoclock
        while True:
            parent_device_name = self.parent_lookup[device_name]
            connection = self.connection_lookup[device_name]
            parent_device_class = getattr(labscript, self.class_lookup[parent_device_name])
            if issubclass(parent_device_class, labscript.PseudoClock):
                # We found the device's clock. Extract the array of
                # clock ticks depending on the clock type:
                clock_type = {'fast clock':'FAST_CLOCK','slow clock':'SLOW_CLOCK'}[connection]
                clock_array = h5_file['devices'][parent_device_name][clock_type]
                return array(clock_array)
            # Nope, this device is not our clock. Go up another level in the family tree:
            device_name = parent_device_name
        






