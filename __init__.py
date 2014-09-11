import os
import platform
import shutil

# Ensure the extension is built, and for the right platform
if __name__ == '__main__':
    raise RuntimeError('Due to funny import rules, this file can\'t be run as __main__.' +
                       'please do \'import runmanager\' to run it.')

def rename_extension_file():
    arch = platform.architecture()
    if arch == ('32bit', 'WindowsPE'):
        name = 'resample32.pyd'
        newname = 'resample.pyd'
    elif arch == ('64bit', 'WindowsPE'):
        name = 'resample64.pyd'
        newname = 'resample.pyd'
    elif arch == ('32bit', 'ELF'):
        name = 'resample32.so'
        newname = 'resample.so'
    elif arch == ('64bit', 'ELF'):
        name = 'resample64.so'
        newname = 'resample.so'
    else:
        raise RuntimeError('Unsupported platform, please report a bug')
    shutil.copy(name, newname)
        
try:
    import resample
except ImportError:
    old_working_directory = os.getcwd()
    runviewer_dir = os.path.dirname(os.path.realpath(__file__))
    try:
        os.chdir(runviewer_dir)
        try:
            rename_extension_file()
        except IOError:
            os.system('python setup.py build_ext --inplace')
            rename_extension_file()
            import resample
    finally:
        os.chdir(old_working_directory)
