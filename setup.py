import sys, os, platform
from setuptools import setup, Extension

# Portable baseline by default; CPU-specific speed via RISSA_NATIVE=1.
# -march=native / -mavx2 can emit instructions (AVX2) that fault with
# "illegal instruction" on older/distribution machines, so published wheels
# must use the portable baseline. The 141-308x wins were measured with
# w64devkit GCC 16.2 on x86-64 with RISSA_NATIVE=1.
# MSVC path (/O2 /arch:AVX2) only with explicit --compiler=msvc (opt-in).
_native = os.environ.get("RISSA_NATIVE") == "1"
_args = " ".join(sys.argv)
if "--compiler=msvc" in _args or "msvc" in _args:
    compile_args = ['/O2', '/arch:AVX2']  # explicit MSVC path (opt-in)
elif sys.platform == "win32":
    compile_args = ['-O3']  # MinGW path, see setup.cfg; portable baseline
    if _native:
        compile_args += ['-mavx2', '-march=native']
else:
    compile_args = ['-O3']
    if _native and platform.machine().lower() in ("x86_64", "amd64"):
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
    Extension(
        'rissa.c_trans',
        sources=['rissa/c_trans.c'],
        extra_compile_args=compile_args,
    ),
    Extension(
        'rissa.c_huff',
        sources=['rissa/c_huff.c'],
        extra_compile_args=compile_args,
    ),
    Extension(
        'rissa.c_stat',
        sources=['rissa/c_stat.c'],
        extra_compile_args=compile_args,
    ),
]

setup(ext_modules=extensions)
