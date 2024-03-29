#!/usr/bin/env python3

"""Bolt OS packaging scripts and tools."""

import os

from setuptools import setup, find_packages
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

VERSION = os.environ.get("BOLT_DISTRO_TOOLS_VERSION", "0.0.0")

setup(
    name='bolt-package',
    version=VERSION,
    url='https://github.com/boltlinux/bolt-distro-tools',
    author='Tobias Koch',
    author_email='tobias.koch@gmail.com',
    license='MIT',

    packages=[
        'boltlinux.package',
        'boltlinux.package.boltpack',
        'boltlinux.package.deb2bolt',
    ],
    data_files=[
        ('bin', [
            'bin/bolt-pack',
            'bin/deb2bolt',
        ]),
    ],
    package_data={
        'boltlinux.package.boltpack': [
            "helpers/python.sh",
            "helpers/arch.sh",
            "relaxng/package.rng.xml",
        ],
    },
    package_dir={'': 'lib'},

    platforms=['Linux'],
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3'
    ],

    keywords='Bolt Linux packaging development',
    description='Bolt Linux packaging scripts and tools',
    long_description='Bolt Linux packaging scripts and tools',
)
