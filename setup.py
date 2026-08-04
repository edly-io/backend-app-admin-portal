#!/usr/bin/env python
"""Package metadata for edl-panel."""
import os
import re

from setuptools import find_packages, setup


def get_version(*file_paths):
    """Extract the ``__version__`` string from a file."""
    filename = os.path.join(os.path.dirname(__file__), *file_paths)
    with open(filename, encoding='utf-8') as version_file:
        version_match = re.search(
            r"^__version__ = ['\"]([^'\"]*)['\"]", version_file.read(), re.M,
        )
    if version_match:
        return version_match.group(1)
    raise RuntimeError('Unable to find version string.')


def is_requirement(line):
    """Return True if the line is an installable requirement."""
    return line and line.strip() and not line.startswith(('-r', '#', '-e', 'git+', '-c'))


def load_requirements(*paths):
    """Load requirement strings from the given .in files."""
    requirements = []
    for path in paths:
        with open(path, encoding='utf-8') as reqs:
            requirements.extend(line.strip() for line in reqs if is_requirement(line))
    return requirements


VERSION = get_version('edl_panel', '__init__.py')
README = open(os.path.join(os.path.dirname(__file__), 'README.rst'), encoding='utf-8').read()

setup(
    name='edl-panel',
    version=VERSION,
    author='EDL Platform',
    description='EDL self-serve admin panel: user and course enrollment management for Open edX.',
    long_description=README,
    long_description_content_type='text/x-rst',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.11',
        'Natural Language :: English',
    ],
    packages=find_packages(
        include=['edl_panel', 'edl_panel.*'],
        exclude=['*tests'],
    ),
    include_package_data=True,
    install_requires=load_requirements('requirements/base.in'),
    python_requires='>=3.11',
    zip_safe=False,
    entry_points={
        'lms.djangoapp': [
            'edl_panel = edl_panel.apps:EdlPanelConfig',
        ],
    },
)
