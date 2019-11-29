# This is a shim to the real __main__.py. See __init__.py in this directory for an
# explanation. Redirecting this file in addition to the package is necessary since the
# launchers execute this file directly, not via import machinery
import runpy
import os
here = os.path.dirname(os.path.realpath(__file__))
name = os.path.basename(here)
runpy.run_path(os.path.join(here, name, '__main__.py'), run_name='__main__')