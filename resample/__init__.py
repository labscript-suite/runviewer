from __future__ import print_function, unicode_literals, division, absolute_import
from labscript_utils import PY2
if PY2:
    str = unicode
import sys
import os
import platform
import importlib


def ensure_extensions_compiled(names, msg=None):
    """Ensure the Cython extensions with the given list of names is compiled, and
    compile by running setup.py if not. Print msg to stderr if compilation is
    required."""
    import shutil
    from os.path import exists, getmtime
    from distutils.sysconfig import get_config_var
    if isinstance(names, str) or isinstance(names, bytes):
        names = [names]
    this_folder = os.path.dirname(os.path.abspath(__file__))
    for name in names:
        extension_pyx = os.path.join(this_folder, name + '.pyx')
        extension_so = os.path.join(this_folder, name)
        ext_suffix = get_config_var('EXT_SUFFIX')
        if ext_suffix is None:
            if os.name == 'nt':
                ext_suffix = '.pyd'
            else:
                ext_suffix = '.so'
        extension_so += ext_suffix
        extension_c = os.path.join(this_folder, name + '.c')
        if (not exists(extension_so)
                or getmtime(extension_so) < getmtime(extension_pyx)):
            current_folder = os.getcwd()
            if msg is not None:
                sys.stderr.write(msg + '\n')
            try:
                os.chdir(this_folder)
                cmd = sys.executable + " setup.py build_ext --inplace"
                if os.name == 'nt':
                    cmd += ' --compiler=msvc'
                if os.system(cmd) != 0:
                    msg = ' '.join(s.strip() for s in """Couldn't compile cython
                          extension. If you are on Windows, ensure you have the
                          following conda packages: libpython, cython, and have
                          installed the appropriate Microsoft visual C or visual
                          studio for your version of Python. If on another
                          platform, ensure you have gcc, libpython, and cython,
                          from conda or otherwise. See above for the specific error
                          that occured""")
                    raise RuntimeError(msg)
                try:
                    shutil.rmtree('build')
                except Exception:
                    pass
                try:
                    os.unlink(extension_c)
                except Exception:
                    pass
            finally:
                os.chdir(current_folder)


# This sub-package is a proxy for the extension. Here we check what platform we are
# on and import the appropriate extension from a sub-package, of which there is one
# for each platform that we have precompiled the extension for. Then we pull out
# the resample function from that extension into this packages namespace so that
# importers see it here without having to know what platform we are on. Importers
# can simply do: 'from runviewer.resample import resample' to get the resample
# function. If the extension has not been compiled for the platform, compilation
# will be attempted at run time, but will fail if there is not a gcc (or mingw),
# cython and libpython.

arch, _ = platform.architecture()
os_platform = sys.platform
plat_name = None
if arch == '32bit' and os_platform == 'win32':
    plat_name = 'win32' if PY2 else 'win32Py3'
elif arch == '64bit' and os_platform == 'win32':
    plat_name = 'win64' if PY2 else 'win64Py3'
elif arch == '64bit' and (os_platform == "linux" or os_platform == "linux2"):
    plat_name = 'linux64' if PY2 else 'linux64Py3'
elif arch == '64bit' and os_platform == "darwin":
    plat_name = 'darwin64' if PY2 else 'darwin64Py3'
else:
    # Try to compile for this platform:
    msg = ("Cython extension has not been precompiled for this platform." +
           "Attempting to compile now, this requires cython, gcc (or mingw) " + 
           "and libpython. If compilation is successful, consider adding " +
           "the compiled extension to this package + "
           "(see runviewer/resample/__init__.py) and submitting a pull request " +
           "to add precompiled support for this platform for everyone.")
    ensure_extensions_compiled(['resample'], msg=msg)
    from runviewer.resample.resample import resample

if plat_name is not None:
    module = importlib.import_module('runviewer.resample.%s.resample' % plat_name)
    resample = module.resample
