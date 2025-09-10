#!/usr/bin/env python3
"""
Setup script for obs-tools package.

This setup.py enables installation via pipx or pip for easier distribution
and avoids ad-hoc venv bootstrapping.
"""

from setuptools import setup, find_packages
import os
import sys

# Ensure we can import from the package
sys.path.insert(0, os.path.dirname(__file__))

def read_requirements():
    """Read requirements from requirements.txt if it exists."""
    req_file = os.path.join(os.path.dirname(__file__), 'requirements.txt')
    if os.path.isfile(req_file):
        with open(req_file, 'r') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    return []

def get_version():
    """Get version from obs_tools.py."""
    try:
        with open('obs_tools.py', 'r') as f:
            content = f.read()
            # Look for version string
            import re
            version_match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
            if version_match:
                return version_match.group(1)
    except:
        pass
    return '1.0.0'

setup(
    name='obs-tools',
    version=get_version(),
    description='Advanced task management system with bidirectional sync between Obsidian and Apple Reminders',
    long_description=open('README.md').read() if os.path.isfile('README.md') else '',
    long_description_content_type='text/markdown',
    author='obs-tools',
    author_email='obs-tools@example.com',
    url='https://github.com/obs-tools/obs-tools',
    
    packages=find_packages(include=['lib', 'tui', 'obs_tools', 'obs_tools.*']),
    py_modules=['obs_tools'],
    
    python_requires='>=3.8',
    
    install_requires=[
        # Core Python dependencies (minimal by design)
    ],
    
    extras_require={
        'macos': [
            'pyobjc>=8.0',
            'pyobjc-framework-EventKit>=8.0',
        ],
        'optimization': [
            'scipy>=1.5.0',  # For Hungarian algorithm optimization
        ],
        'validation': [
            'jsonschema>=3.0.0',  # For schema validation
        ],
        'dev': [
            'pytest>=6.0',
            'pytest-cov>=2.10',
            'black>=21.0',
            'mypy>=0.900',
        ]
    },
    
    entry_points={
        'console_scripts': [
            'obs-tools=obs_tools:main',
            'obs-app=obs_tools:main',
            'obs-sync=obs_tools:main',
            'obs-collect=obs_tools:main',
        ],
    },
    
    include_package_data=True,
    package_data={
        'lib': ['*.py'],
        'tui': ['*.py'],
        'obs_tools': ['*.py'],
        'obs_tools.commands': ['*.py'],
        '': ['Resources/schemas/*.json', 'bin/*'],
    },
    
    data_files=[
        ('bin', ['bin/obs', 'bin/obs-app', 'bin/obs-sync', 'bin/obs-tasks']),
        ('share/obs-tools/schemas', [
            'Resources/schemas/obsidian_tasks_index_v2.json',
            'Resources/schemas/reminders_tasks_index_v2.json', 
            'Resources/schemas/sync_links_v1.json'
        ]),
    ],
    
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Topic :: Office/Business :: Scheduling',
        'Topic :: Text Processing :: Markup',
        'Topic :: Utilities',
    ],
    
    keywords=['obsidian', 'reminders', 'tasks', 'sync', 'productivity', 'markdown'],
    
    project_urls={
        'Bug Reports': 'https://github.com/obs-tools/obs-tools/issues',
        'Source': 'https://github.com/obs-tools/obs-tools',
        'Documentation': 'https://github.com/obs-tools/obs-tools/blob/main/README.md',
    },
)