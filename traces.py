class TraceType(object):
    """Base class for trace types"""
    pass
    
class AI(TraceType):
    """Analog input type"""
    pass
    
class AO(TraceType):
    """Analog output type"""
    pass
    
class DO(TraceType):
    """Digital output type"""
    pass
   
class DDSFreq(TraceType):
    """DDS frequency output type"""
    pass
    
class DDSAmp(TraceType):
    """DDS amplitude output type"""
    pass
    
class DDSPhase(TraceType):
    """DDS phase output type"""
    pass
     
class Trace(object):
    """Object representing a single output trace. A simple container
    for data, rather than using a dictionary"""
    def __init__(self, name, type, times, data, device, connection, labels=[]):
        if not issubclass(type, TraceType):
            raise TypeError('type must be one of the TraceTypes from the runviewer module')
        self.name = name
        self.type = type
        self.times = times
        self.data = data
        self.device = device
        self.connection = connection
        self.labels = labels
