import sys, platform
from setuptools import setup, Extension

# Platform-conditional flags. Windows/MinGW numbers (-O3 -mavx2 -march=native
# = 141-308x wins) were measured with w64devkit GCC 16.2 on x86-64.
# MSVC uses /O2 /arch:AVX2. Non-x86 gets plain -O3 (no AVX2 assumptions).
_args = " ".join(sys.argv)
if "--compiler=msvc" in _args or "msvc" in _args:
    compile_args = ['/O2', '/arch:AVX2']  # explicit MSVC path
elif sys.platform == "win32":
    compile_args = ['-O3', '-mavx2', '-march=native']  # MinGW path, see setup.cfg
else:
    compile_args = ['-O3']
    if platform.machine().lower() in ("x86_64", "amd64"):
        compile_args += ['-mavx2', '-march=native']

# NOTE: rissa.arrow_glue lives on draft/pyarrow-codec only (C++ PR track)
# and is intentionally NOT listed here. See docs/arrow-pr.md on that branch.
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
]

setup(ext_modules=extensions)
