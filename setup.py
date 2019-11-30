# Make a release tarball with:
#
#     `python setup.py sdist`
#
# Upload to test PyPI with:
#
#     `twine upload --repository-url https://test.pypi.org/legacy/ dist/*`
#
# Install from test PyPI with:
#
#     pip install --index-url https://test.pypi.org/simple/ runviewer
#
# Upload to real PyPI with:
#
#     `twine upload dist/*`
#

from setuptools import setup

from runviewer import __version__

#TODO: add labscript suite deps once they are on PyPI
REQUIREMENTS = [
    "autocython",
    "zprocess",
    "qtutils >= 2.0.0",
    "pyqtgraph >= 0.9.10",
    "numpy",
    "scipy",
    "h5py"
]

setup(
    name='runviewer',
    version=__version__,
    description="A program to view shots compiled by labscript",
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author='The labscript suite community',
    author_email='labscriptsuite@googlegroups.com ',
    url='http://labscriptsuite.org',
    license="BSD",
    packages=["runviewer", "runviewer.resample"],
    package_data={'': ['*']},
    include_package_data=True,
    python_requires=">=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*",
    install_requires=REQUIREMENTS
)
