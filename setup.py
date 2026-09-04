import sys
from setuptools import setup, Extension

# These flags gave you the wins on Windows via MinGW
# DO NOT change these unless you switch to MSVC.
compile_args = ['-O3', '-mavx2', '-march=native']

extensions = [
    Extension(
        'rissa.c_shuffle',
        sources=['rissa/c_shuffle.c'],
        extra_compile_args=compile_args,
    ),
    Extension(
        'rissa.c_bit',
        sources=['rissa/c_bit.c'],
        extra_compile_args=compile_args,
    ),
    Extension(
        'rissa.c_delta',
        sources=['rissa/c_delta.c'],
        extra_compile_args=compile_args,
    ),
    Extension(
        'rissa.arrow_glue',
        sources=['rissa/arrow_glue.c'],
        extra_compile_args=compile_args,
    ),
]

setup(ext_modules=extensions)
