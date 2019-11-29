# This is a shim to the real package one subfolder below. It exists for backward
# compatibility with installations from before the restructuring of this project's
# repository into the usual structure for Python packages. This allows these
# installations to continue functioning and being updatable as we switch the
# repositories to the new repo layout one-at-a-time.
import sys
import os
try:
    sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
    del sys.modules[__name__]
    __import__(__name__)
finally:
    del sys.path[0]
