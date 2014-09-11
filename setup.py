# run as python setup.py build_ext --inplace

from distutils.core import setup, Extension
import numpy
import os
import platform

setup(
    ext_modules = [
        Extension("resample",sources=["resample.c"], include_dirs = [numpy.get_include()])
        ]
    )
    
arch = platform.architecture()
if arch == ('32bit', 'WindowsPE'):
    oldname = 'resample.pyd'
    newname = 'resample32.pyd'
elif arch == ('64bit', 'WindowsPE'):
    oldname = 'resample.pyd'
    newname = 'resample64.pyd'
elif arch == ('32bit', 'ELF'):
    oldname = 'resample.so'
    newname = 'resample32.so'
elif arch == ('64bit', 'ELF'):
    oldname = 'resample.so'
    newname = 'resample64.so'
else:
    raise RuntimeError('Unsupported platform, please report a bug')
    
os.rename(oldname, newname)