from pylab import *

from runviewer.traces import Trace, AO, AI, DO, DDSFreq, DDSAmp, DDSPhase

def decompose_bitfield(intarray,nbits):
        """converts a single array of unsigned ints into a 2D array
        (len(intarray) x nbits) of ones and zeros"""
        bitarray = zeros((len(intarray), nbits), dtype=int8)
        for i in range(nbits):
            bitarray[:,i] = (intarray & (1 << i)) >> i
        return bitarray
        
def NI_card(h5_file, device_name, clock, name_lookup, n_digitals):
    device_group = h5_file['devices'][device_name]
    try:
        analog_outs = device_group['ANALOG_OUTS']
    except KeyError:
        analog_outs = None
    try:
        digital_outs = device_group['DIGITAL_OUTS']
    except KeyError:
        digital_outs = None
    try:
        acquisitions = device_group['ACQUISITIONS']
    except KeyError:
        acquisitions = None
    traces = []
    if analog_outs is not None:
        analog_channels = device_group.attrs['analog_out_channels']
        analog_channels = [channel.split('/')[1] for channel in analog_channels.split(',')]
        for i, chan in enumerate(analog_channels):
            data = analog_outs[:,i]
            name = name_lookup[device_name, chan]
            trace = Trace(name=name, type=AO, times=clock, data = array(data),
                          device=device_name, connection=chan)
            traces.append(trace)
    if digital_outs is not None:
        digital_bits = decompose_bitfield(digital_outs[:],n_digitals)
        for i in range(32):
            connection = (device_name,'port0/line%d'%i)
            if connection in name_lookup:
                data = digital_bits[:,i]
                name = name_lookup[connection]
                trace = Trace(name=name, type=DO, times=clock, data=array(data),
                              device=device_name, connection=connection[1])
                traces.append(trace)
    if acquisitions is not None:
        input_chans = {}
        for i, acquisition in enumerate(acquisitions):
            chan = acquisition['connection']
            if chan not in input_chans:
                input_chans[chan] = []
            input_chans[chan].append(acquisition)
        for chan in input_chans:
            name = name_lookup[device_name, chan]
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
            trace = Trace(name=name, type=AI, times=array(times), data=array(gate),
                          device=device_name, connection=chan,labels=labels)
            traces.append(trace)
    return traces
        
def NI_PCIe_6363(h5_file, device_name, clock, name_lookup):
    n_digitals = 32
    return NI_card(h5_file, device_name, clock, name_lookup, n_digitals)
    
    
def NI_PCI_6733(h5_file, device_name, clock, name_lookup):
    n_digitals = 0
    return NI_card(h5_file, device_name, clock, name_lookup, n_digitals)
    
    
def NovaTechDDS9M(h5_file, device_name, clock, name_lookup):
    device_group = h5_file['devices'][device_name]
    try:
        table_data = device_group['TABLE_DATA']
    except KeyError:
        table_data = None
    try:
        static_data = device_group['STATIC_DATA']
    except KeyError:
        static_data = None
    traces = []
    if table_data is not None:
        for i in range(2):
            connection = (device_name, 'channel %d'%i)
            if connection in name_lookup:
                name = name_lookup[connection]
                freqs = table_data['freq%d'%i]
                amps = table_data['amp%d'%i]
                phases = table_data['phase%d'%i]
                freqtrace = Trace(name=name + '_freq', type=DDSFreq, times=clock, data=array(freqs),
                                  device=device_name, connection=connection[1])
                amptrace = Trace(name=name + '_amp', type=DDSAmp, times=clock, data=array(amps),
                                 device=device_name, connection=connection[1])
                phasetrace = Trace(name=name + '_phase', type=DDSPhase, times=clock, data=array(phases),
                                   device=device_name, connection=connection[1])
                traces.extend([freqtrace, amptrace, phasetrace])
    if static_data is not None:
        for i in [2,3]:
            connection = (device_name, 'channel %d'%i)
            if connection in name_lookup:
                name = name_lookup[connection]
                freqs = zeros(len(clock)) + static_data['freq%d'%i][0]
                amps = zeros(len(clock)) + static_data['amp%d'%i][0]
                phases = zeros(len(clock)) + static_data['phase%d'%i][0]
                freqtrace = Trace(name=name + '_freq', type=DDSFreq, times=clock, data=array(freqs),
                                  device=device_name, connection=connection[1])
                amptrace = Trace(name=name + '_amp', type=DDSAmp, times=clock, data=array(amps),
                                 device=device_name, connection=connection[1])
                phasetrace = Trace(name=name + '_phase', type=DDSPhase, times=clock, data=array(phases),
                                   device=device_name, connection=connection[1])
                traces.extend([freqtrace, amptrace, phasetrace])
    return traces
    
    
def PulseBlaster(h5_file, device_name, clock, name_lookup):
    device_group = h5_file['devices'][device_name]
    # As we are a Pseudoclock, the argument 'clock', passed in above, is None.
    # We are responsible for extracting our own clock:
    clock = array(device_group['SLOW_CLOCK'])
    pulse_program = device_group['PULSE_PROGRAM']
    clock_indices = device_group['CLOCK_INDICES']
    flags = empty(len(clock), dtype = uint32)
    states = pulse_program[clock_indices]
    flags = states['flags']
    flags = decompose_bitfield(flags, 12)
    traces = []
    for i in range(12):
        connection = (device_name, 'flag %d'%i)
        if connection in name_lookup:
            name = name_lookup[connection]
            data = flags[:,i]
            trace = Trace(name=name, type=DO, times=clock, data=array(data),
                          device=device_name, connection=connection[1])
            traces.append(trace)
    for i in range(2):
        connection = (device_name, 'dds %d'%i)
        if connection in name_lookup:
            name = name_lookup[connection]
            freqtable = device_group['DDS%d'%i]['FREQ_REGS']
            amptable = device_group['DDS%d'%i]['AMP_REGS']
            phasetable = device_group['DDS%d'%i]['PHASE_REGS']
            freqregs = states['freq%d'%i]
            ampregs = states['amp%d'%i]
            phaseregs = states['phase%d'%i]
            freqs = array(freqtable)[freqregs]
            amps = array(amptable)[ampregs]
            phases = array(phasetable)[phaseregs]
            freqtrace = Trace(name=name + '_freq', type=DDSFreq, times=clock, data=array(freqs), 
                              device=device_name, connection=connection[1])
            amptrace = Trace(name=name + '_amp', type=DDSAmp, times=clock, data=array(amps), 
                             device=device_name, connection=connection[1])
            phasetrace = Trace(name=name + '_phase', type=DDSPhase, times=clock, data=array(phases),
                               device=device_name, connection=connection[1])
            traces.extend([freqtrace, amptrace, phasetrace])
    return traces
    
    
def RFBlaster(h5_file, device_name, clock, name_lookup):
    device_group = h5_file['devices'][device_name]
    table_data = device_group['TABLE_DATA']
    # As we are a Pseudoclock, the argument 'clock', passed in above, is None.
    # We are responsible for extracting our own clock:
    clock = array(table_data['time'])
    traces = []
    for i in range(2):
        connection = (device_name, 'channel %d'%i)
        if connection in name_lookup:
            name = name_lookup[connection]
            freqs = table_data['freq%d'%i]
            amps = table_data['amp%d'%i]
            phases = table_data['phase%d'%i]
            freqtrace = Trace(name=name + '_freq', type=DDSFreq, times=clock, data=array(freqs), 
                              device=device_name, connection=connection[1])
            amptrace = Trace(name=name + '_amp', type=DDSAmp, times=clock, data=array(amps), 
                             device=device_name, connection=connection[1])
            phasetrace = Trace(name=name + '_phase', type=DDSPhase, times=clock, data=array(phases),
                               device=device_name, connection=connection[1])
            traces.extend([freqtrace, amptrace, phasetrace])
    return traces
    
    
def Camera(h5_file, device_name, clock, name_lookup):
    return []
