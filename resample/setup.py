# This extension is intended to be built with autocython. To trigger a build on a
# new platform, run the code that imports the extension, or run:
# python -m autocython
# in this directory.
from setuptools import setup
from setuptools.extension import Extension
from Cython.Distutils import build_ext
from autocython import PLATFORM_SUFFIX
ext_modules = [Extension("resample" + PLATFORM_SUFFIX, ["resample.pyx"])]
setup(
    name = "resample",
    cmdclass = {"build_ext": build_ext},
    ext_modules = ext_modules
)
