from __future__ import print_function, unicode_literals, division, absolute_import
from labscript_utils import PY2, check_version
if PY2:
    str = unicode
import os

try:
    import autocython
except ImportError:
    msg = ('autocython required, installable via pip')
    raise RuntimeError(msg)

check_version('autocython', '1.1', '2.0')
from autocython import ensure_extensions_compiled, import_extension

ensure_extensions_compiled(os.path.abspath(os.path.dirname(__file__)))
extension = import_extension('runviewer.resample.resample')
resample = extension.resample
