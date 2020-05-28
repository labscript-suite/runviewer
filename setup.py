import os
from setuptools import setup
from setuptools.extension import Extension
from Cython.Distutils import build_ext


CMDCLASS = {"build_ext": build_ext}


VERSION_SCHEME = {
    "version_scheme": os.getenv("SCM_VERSION_SCHEME", "guess-next-dev"),
    "local_scheme": os.getenv("SCM_LOCAL_SCHEME", "node-and-date"),
}


EXT_MODULES = [
    Extension("runviewer.resample", sources=[os.path.join("src", "resample.pyx")])
]

setup(
    use_scm_version=VERSION_SCHEME,
    cmdclass=CMDCLASS,
    ext_modules=EXT_MODULES,
)
