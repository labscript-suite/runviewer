from distutils.core import setup, Extension
import numpy

setup(
    ext_modules = [
        Extension("resample",sources=["resample.c"], include_dirs = [numpy.get_include()])
        ]
    )
    
import shutil, os
if os.name == 'posix':
    shutil.copy('build/lib.linux-x86_64-2.6/resample.so','resample.so')
    shutil.rmtree('build')
