#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

import os
import sys
from setuptools import setup, find_packages

# Try to import DistUtilsExtra for i18n support, but make it optional
try:
    import DistUtilsExtra.command.build_extra
    import DistUtilsExtra.command.build_i18n
    import DistUtilsExtra.command.clean_i18n
    HAS_DISTUTILS_EXTRA = True
except ImportError:
    HAS_DISTUTILS_EXTRA = False
    print("Warning: DistUtilsExtra not found. i18n features will be disabled.")

# to update i18n .mo files (and merge .pot file into .po files):
# python setup.py build_i18n -m

for line in open('software-station').readlines():
    if line.startswith('__VERSION__'):
        exec(line.strip())
        break
else:
    __VERSION__ = '2.0'

PROGRAM_VERSION = __VERSION__


def datafilelist(installbase, sourcebase):
    datafileList = []
    for root, subFolders, files in os.walk(sourcebase):
        fileList = []
        for f in files:
            fileList.append(os.path.join(root, f))
        datafileList.append((root.replace(sourcebase, installbase), fileList))
    return datafileList


prefix = sys.prefix

data_files = [
    (f'{prefix}/share/applications', ['software-station.desktop']),
    (f'{prefix}/etc/sudoers.d', ['sudoers.d/software-station']),
]

# Only add locale files if they exist
if os.path.isdir('build/mo'):
    data_files.extend(datafilelist(f'{prefix}/share/locale', 'build/mo'))

# Only set up i18n commands if DistUtilsExtra is available
if HAS_DISTUTILS_EXTRA:
    cmdclass = {
        "build": DistUtilsExtra.command.build_extra.build_extra,
        "build_i18n": DistUtilsExtra.command.build_i18n.build_i18n,
        "clean": DistUtilsExtra.command.clean_i18n.clean_i18n,
    }
else:
    cmdclass = {}

setup(
    name="software-station",
    version=PROGRAM_VERSION,
    description="GhostBSD software manager",
    license='BSD',
    author='Eric Turgeon',
    url='https://github.com/GhostBSD/software-station/',
    package_dir={'': '.'},
    packages=['software_station'],
    package_data={
        'software_station': [
            '__init__.py',
            'icons.py',
            'desktop_index.py',
            'pkg_desktop_map.py',
            'accessories_map.py',
        ],
    },
    data_files=data_files,
    install_requires=['setuptools'],
    py_modules=["software_station_pkg", "software_station_xpm", "iconlist"],
    scripts=['software-station'],
    cmdclass=cmdclass,
    python_requires='>=3.11',
)
