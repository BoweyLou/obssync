#!/usr/bin/env python3
"""
Setup script for obs-sync package.

This file exists for backward compatibility with tools that expect setup.py.
All package metadata is now defined in pyproject.toml (PEP 621).

Note: py_modules parameter is specified here because it's not supported
in pyproject.toml's [tool.setuptools] section as of setuptools 69+.
"""

from setuptools import setup

# All configuration is in pyproject.toml except py_modules
setup(
    py_modules=["obs_tools"],
)