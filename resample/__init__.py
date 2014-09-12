import os
import platform
import shutil
import importlib

# This sub-package is a proxy for the extensension file that abstracts the platform.
# Here we check what platform we are on and we import the appropriate extension from
# yet another sub-package, of which there is one for each supported platform.
# Then we pull out the resample function from that extension into this packages namespace
# so that importers see it here without having to know what platform we are on.
# Importers can simply do: 'from runviewer.resample import resample' to get the resample function.

if __name__ == '__main__':
    raise RuntimeError('Due to funny import rules, this file can\'t be run as __main__.' +
                       'please do \'import runmanager.resample\' from elsewhere to run it.')

arch = platform.architecture()
if arch == ('32bit', 'WindowsPE'):
    plat_name = 'win32'
    file_name = 'resample.pyd'
elif arch == ('64bit', 'WindowsPE'):
    plat_name = 'win64'
    file_name = 'resample.pyd'
elif arch == ('32bit', 'ELF'):
    plat_name = 'unix32'
    file_name = 'resample.so'
elif arch == ('64bit', 'ELF'):
    plat_name = 'unix64'
    file_name = 'resample.so'
else:
    raise RuntimeError('Unsupported platform, please report a bug')
    
module = importlib.import_module('runviewer.resample.%s.resample'%plat_name)

resample = module.resample