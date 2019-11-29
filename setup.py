from setuptools import setup

from runviewer import __version__

DESCRIPTION = ("A program to view shots compiled by labscript" )

setup(name='runviewer',
      version=__version__,
      description=DESCRIPTION,
      long_description=open('README.md').read(),
      long_description_content_type='text/markdown',
      author='The labscript suite community',
      author_email='labscriptsuite@googlegroups.com ',
      url='labscriptsuite.org',
      license="BSD",
      py_modules=["inotify_simple"],
      python_requires=">2.7, !=3.0.*, !=3.1.*"
      )
