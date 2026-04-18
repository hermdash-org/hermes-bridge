"""
Setup — Compile bridge Python files to C extensions via Cython.

Used in Docker multi-stage build to obfuscate source code.
Only compiled .so files ship in the final image.
"""

from setuptools import setup, find_packages
from Cython.Build import cythonize
import os

# Find all .py files in bridge/ (except __init__.py which must stay as .py)
py_files = []
for root, dirs, files in os.walk("bridge"):
    for f in files:
        if f.endswith(".py") and f != "__init__.py":
            py_files.append(os.path.join(root, f))

setup(
    name="hermes-bridge",
    version="1.0.0",
    ext_modules=cythonize(
        py_files,
        compiler_directives={
            "language_level": "3",
        },
    ),
    packages=find_packages(),
)
