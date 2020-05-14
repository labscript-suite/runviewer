import os
from setuptools import setup
from setuptools.dist import Distribution

try:
    from setuptools_conda import dist_conda
    CMDCLASS = {"dist_conda": dist_conda}
except ImportError:
    CMDCLASS = {}

if "CONDA_BUILD" not in os.environ:
    dist = Distribution()
    dist.parse_config_files()
    INSTALL_REQUIRES = dist.command_options["options"]["install_requires"][1]
    INSTALL_REQUIRES = INSTALL_REQUIRES.strip().split('\n')
else:
    INSTALL_REQUIRES = []

VERSION_SCHEME = {}
VERSION_SCHEME["version_scheme"] = os.environ.get(
    "SCM_VERSION_SCHEME", "guess-next-dev"
)
VERSION_SCHEME["local_scheme"] = os.environ.get("SCM_LOCAL_SCHEME", "node-and-date")

setup(
    use_scm_version=VERSION_SCHEME,
    cmdclass=CMDCLASS,
    install_requires=INSTALL_REQUIRES
)
