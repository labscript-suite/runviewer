# This is a shim to the real __main__.py. See __init__.py in this directory for an
# explanation. Redirecting this file in addition to the package is necessary since the
# launchers execute this file directly, not via import machinery. This file will fix the
# lasunchers, if labscript_utils is new enough, to point to the real __main__.py.

import sys
import os
here = os.path.dirname(os.path.realpath(__file__))
name = os.path.basename(here)
if os.name == 'nt':
    from labscript_utils import check_version, VersionException
    # If labscript_utils is new enough, fix the shortcuts so that they point to the new
    # location of __main__.py, then run the new shortcut and quit
    try:
        check_version('labscript_utils', '2.15', '3')
    except VersionException:
        pass
    else:
        from labscript_utils import labscript_suite_profile
        from labscript_utils.winshell import fix_shortcuts, launcher_name
        fix_shortcuts()
        shortcut = os.path.join(labscript_suite_profile, launcher_name(name))
        os.startfile(shortcut)
        sys.exit(0)

# Otherwise just run the real __main__.py. The user will get an error saying
# to update labscript_utils
import runpy
runpy.run_path(os.path.join(here, name, '__main__.py'), run_name='__main__')