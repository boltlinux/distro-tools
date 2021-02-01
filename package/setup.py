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
    url='https://github.com/tobijk/bolt-package',
    author='Tobias Koch',
    author_email='tobias.koch@gmail.com',
    license='MIT',
    packages=[
        'boltlinux.package',
        'boltlinux.package.boltpack',
        'boltlinux.package.deb2bolt',
    ],
    package_dir={'': 'lib'},
    data_files=[
        ('bin', [
            'bin/bolt-pack',
            'bin/deb2bolt',
        ]),
        ('share/bolt-pack/relaxng', ['relaxng/package.rng.xml']),
        ('share/bolt-pack/helpers', [
            'helpers/arch.sh',
            'helpers/python.sh'
        ])
    ],
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
