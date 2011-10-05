from distutils.core import setup, Extension

setup(
    ext_modules = [
        Extension("resample",sources=["resample.c"])
        ]
    )
    
import shutil, os
if os.name == 'posix':
    shutil.copy('build/lib.linux-x86_64-2.6/resample.so','resample.so')
    shutil.rmtree('build')
