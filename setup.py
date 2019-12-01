# USAGE NOTES
#
# Make a PyPI release tarball with:
#
#     python setup.py sdist
#
# Upload to test PyPI with:
#
#     twine upload --repository-url https://test.pypi.org/legacy/ dist/*
#
# Install from test PyPI with:
#
#     pip install --index-url https://test.pypi.org/simple/ runviewer
#
# Upload to real PyPI with:
#
#     twine upload dist/*
#
# Build conda packages for all platforms (in a conda environment with conda-build and
# conda-verify installed) with:
#
#     python setup.py conda_dist
#
# Upoad to your own account (for testing) on anaconda cloud (in a conda environment with
# anaconda-client installed) with:
#
#     anaconda upload --skip-existing
#          conda_dist/linux-64/* dist_conda/osx-64/*
#          conda_dist/win-32/* conda_dist/win-64/*
#
# (This command can be shorter on Unix, but Windows won't recursively expand wildcards)
#
# Upoad to the labscript-suite organisation's channel on anaconda cloud (in a
# conda environment with anaconda-client installed) with:
#
#     anaconda -c labscript-suite upload --skip-existing
#          conda_dist/linux-64/* conda_dist/osx-64/*
#          conda_dist/win-32/* conda_dist/win-64/*
#
# If you need to rebuild the same version of the package for conda due to a packaging
# issue, you must increment CONDA_BUILD_NUMBER in order to create a unique version on
# anaconda cloud. When subsequently releasing a new version of the package,
# CONDA_BUILD_NUMBER should be reset to zero.

import os
import runviewer
from setuptools import setup

try:
    from setuptools_conda import conda_dist
except ImportError:
    conda_dist = None

SETUP_REQUIRES = ['setuptools', 'setuptools_scm']

# TODO: add labscript suite deps once they are on PyPI/anaconda cloud
INSTALL_REQUIRES_CONDA = [
    "pyqtgraph >=0.9.10",
    "numpy >=1.15",
    "scipy",
    "h5py",
]

INSTALL_REQUIRES = INSTALL_REQUIRES_CONDA + [
    "autocython",
    "zprocess",
    "qtutils >= 2.0.0",
]

setup(
    name='runviewer',
    version=runviewer.__version__,
    description="A program to view shots compiled by labscript",
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author='The labscript suite community',
    author_email='labscriptsuite@googlegroups.com ',
    url='http://labscriptsuite.org',
    license="BSD",
    packages=["runviewer", "runviewer.resample"],
    zip_safe=False,
    setup_requires=SETUP_REQUIRES,
    include_package_data=True,
    python_requires=">=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*, !=3.5",
    install_requires=INSTALL_REQUIRES if 'CONDA_BUILD' not in os.environ else [],
    cmdclass={'conda_dist': conda_dist} if conda_dist is not None else {},
    command_options={
        'conda_dist': {
            'pythons': (__file__, ['2.7', '3.6', '3.7']),
            'platforms': (__file__, 'all'),
            'force_conversion': (__file__, 1),
        },
    },
)
