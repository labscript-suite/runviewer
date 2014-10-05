# run as python setup.py build_ext --inplace.
# This will build the extension file in this directory.
# You must then put it in the appropriate platform-named
# subdirectory with an empty __init__.py in order for it
# to be importable.

from distutils.core import setup, Extension
import numpy

setup(
    ext_modules = [
        Extension("resample",sources=["resample.c"], include_dirs = [numpy.get_include()])
        ]
    )
