# USAGE NOTES
#
# Make a PyPI release tarball with:
#
#     `python setup.py sdist`
#
# Upload to test PyPI with:
#
#     `twine upload --repository-url https://test.pypi.org/legacy/ dist/*`
#
# Install from test PyPI with:
#
#     `pip install --index-url https://test.pypi.org/simple/ runviewer`
#
# Upload to real PyPI with:
#
#     `twine upload dist/*`
#
# Build conda packages for all platforms (in a conda environment with conda-build and
# conda-verify installed) with:
#
#     `python setup.py conda_dist`
#
# Upoad to your own account (for testing) on anaconda cloud (in a conda environment with
# anaconda-client installed) with:
#
#     `anaconda upload --skip-existing
#          conda_dist/linux-64/* dist_conda/osx-64/*
#          conda_dist/win32/* conda_dist/win-64/*`
#
# (This command can be shorter on Unix, but Windows won't recursively expand wildcards)
#
#Upoad to the labscript-suite organisation's channel on anaconda cloud (in a
# conda environment with anaconda-client installed) with:
#
#     `anaconda -c labscript-suite upload --skip-existing
#          conda_dist/linux-64/* conda_dist/osx-64/*
#          conda_dist/win32/* conda_dist/win-64/*`
#
# If you need to rebuild the same version of the package for conda due to a packaging
# issue, you must increment CONDA_BUILD_NUMBER in order to create a unique version on
# anaconda cloud. When subsequently releasing a new version of the package,
# CONDA_BUILD_NUMBER should be reset to zero.

import os
from setuptools import setup, Command
from string import Template
import runviewer
import shutil
import hashlib
from subprocess import check_call
from glob import glob

NAME = 'runviewer'
VERSION = runviewer.__version__
HOME = 'http://labscriptsuite.org'
LICENSE = "BSD"
LICENSE_FILE = 'LICENSE.txt'
SUMMARY = "A program to view shots compiled by labscript"

CONDA_PYTHONS = ['2.7', '3.5', '3.6', '3.7']
CONDA_PLATFORMS = ['osx-64', 'linux-64', 'win-32', 'win-64']
CONDA_BUILD_NUMBER = 0

PYTHON_REQUIRES = ">=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*"
SETUP_REQUIRES = ['setuptools', 'setuptools_scm']

# TODO: add labscript suite deps once they are on PyPI
INSTALL_REQUIRES = [
    # "autocython",
    # "zprocess",
    # "qtutils >= 2.0.0",
    "pyqtgraph >=0.9.10",
    "numpy >=1.15",
    "scipy",
    "h5py",
]


class conda_dist(Command):
    description = "Make conda packages"
    user_options = []
    RECIPE_DIR = 'conda_build'
    DIST_DIR = 'conda_dist'
    initialize_options = finalize_options = lambda self: None

    def run(self):
        CONDA_PREFIX = os.getenv('CONDA_PREFIX', None)
        if CONDA_PREFIX is None:
            raise RuntimeError("Must activate a conda environment to run build_conda")
        tarball = os.path.join('dist', NAME + '-' + VERSION + '.tar.gz')
        build_config_yaml = os.path.join(self.RECIPE_DIR, 'conda_build_config.yaml')
        shutil.rmtree(self.RECIPE_DIR, ignore_errors=True)
        os.mkdir(self.RECIPE_DIR)
        if not os.path.exists(tarball):
            msg = "Source tarball %s not found, run `sdist` before `build_conda`"
            raise RuntimeError(msg % tarball)
        template = Template(open('conda_build_config.yaml.template').read())
        with open(build_config_yaml, 'w') as f:
            f.write(template.substitute(CONDA_PYTHONS='\n  - '.join(CONDA_PYTHONS)))
        template = Template(open('meta.yaml.template').read())
        with open(os.path.join(self.RECIPE_DIR, 'meta.yaml'), 'w') as f:
            f.write(
                template.substitute(
                    NAME=NAME,
                    VERSION=VERSION,
                    TARBALL=tarball,
                    SHA256=hashlib.sha256(open(tarball, 'rb').read()).hexdigest(),
                    BUILD_NUMBER=CONDA_BUILD_NUMBER,
                    BUILD_REQUIRES='\n    - '.join(SETUP_REQUIRES),
                    RUN_REQUIRES='\n    - '.join(INSTALL_REQUIRES),
                    HOME=HOME,
                    LICENSE=LICENSE,
                    LICENSE_FILE=LICENSE_FILE,
                    SUMMARY=SUMMARY,
                )
            )
        check_call(['conda-build', self.RECIPE_DIR])
        if not os.path.exists(self.DIST_DIR):
            os.mkdir(self.DIST_DIR)
        builds_glob = [
            CONDA_PREFIX,
            'conda-bld',
            '*',
            '%s-%s-py*_%d.tar.bz2' % (NAME, VERSION, CONDA_BUILD_NUMBER),
        ]
        convert_cmd = ['conda-convert', '-f', '-o', self.DIST_DIR]
        for platform in CONDA_PLATFORMS:
            convert_cmd += ['-p', platform]
        for path in glob(os.path.join(*builds_glob)):
            platform = os.path.basename(os.path.dirname(path))
            if platform in CONDA_PLATFORMS:
                destdir = os.path.join(self.DIST_DIR, platform)
                if not os.path.exists(destdir):
                    os.mkdir(destdir)
                shutil.copy(path, destdir)
                convert_cmd.append(path)
        check_call(convert_cmd)


setup(
    name=NAME,
    version=VERSION,
    description=SUMMARY,
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author='The labscript suite community',
    author_email='labscriptsuite@googlegroups.com ',
    url=HOME,
    license=LICENSE,
    packages=["runviewer", "runviewer.resample"],
    zip_safe=False,
    setup_requires=SETUP_REQUIRES,
    include_package_data=True,
    python_requires=PYTHON_REQUIRES,
    # Conda build chokes on the install dependencies at build time, they are not needed
    # for building so ignore them:
    install_requires=INSTALL_REQUIRES if 'CONDA_BUILD' not in os.environ else [],
    cmdclass={'conda_dist': conda_dist},
    # Create both a tarball and a zip file, instead of the archive type being
    # platform-dependent. This is important since the conda build needs a tarball. And
    # we might as well make a zipfile too for windows users manually downloading it.
    command_options={'sdist': {'formats': ('setup.py', 'gztar,zip')}},
)
