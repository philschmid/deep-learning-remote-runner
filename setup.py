from __future__ import absolute_import
import os
from datetime import date
from setuptools import find_packages, setup

# We don't declare our dependency on transformers here because we build with
# different packages for different variants

VERSION = "0.0.1"

install_requires = ["boto3", "paramiko", "scp", "nanoid"]

extras = {}

extras["quality"] = [
    "black==21.4b0",
    "isort>=5.5.4",
    "flake8>=3.8.3",
]

setup(
    name="rm_runner",
    version=VERSION,
    author="Philipp Schmid",
    description="A CLI/SDK to run remote scripts on ec2 via ssh/scp",
    url="https://github.com/philschmid/deep-learning-remote-runner",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=install_requires,
    extras_require=extras,
    # entry_points={"console_scripts": "ec2ssh=ec2ssh.main:main"},
    python_requires=">=3.8.0",
    license="Apache License 2.0",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Intended Audience :: Education",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
    ],
)
