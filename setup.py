#!/usr/bin/env python3
"""Setup script for cli-tool."""
from setuptools import setup, find_packages

setup(
    name='cli-tool',
    version='0.1.0',
    description='A tmux wrapper for LLMs to interact with full-screen CLI applications',
    author='cli-tool team',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[],
    entry_points={
        'console_scripts': [
            'cli-tool=cli_tool.main:main',
        ],
    },
    python_requires='>=3.6',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
    ],
)