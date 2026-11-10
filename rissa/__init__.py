"""
rissa - https://rissa.web.app
import rissa; rissa.compress(data, level=3)

Public API (stable): compress() writes the v3 container; decompress() reads
any version (v2/v3/v4 dispatch). Containers: v3 default, v4 opt-in via
deep_compress.compressor_v4. Internals: deep_compress.* (escape hatches).
"""
__version__ = "4.6.6"
__author__ = "rissa (Rissanen MDL 1978)"
import os
import sys
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from deep_compress.api_types import Backend
for _p in (os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")),
           os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "deep_compress"))):
    if _p not in sys.path:
        sys.path.insert(0, _p)
del _p

# NOTE: deep_compress imports are LAZY (inside functions), not top-level.
# Top-level `from deep_compress... import ...` here created a circular import:
# whoever imported deep_compress.compressor_v3 FIRST got a partially-initialized
# back-import, rissa/__init__ raised, and every HAS_C_* flag silently went False
# (all C extensions disabled with zero warning). Lazy binding fixes all entry
# orders: `import rissa`, `import deep_compress.x`, scripts, and frozen exe.

def _map_level(level: int, backend: str) -> int:
    """Map portable 1-4 to backend-native levels; other ints pass through clamped."""
    if level == 1:
        return {"zstd": 3, "zlib": 1, "lzma": 0, "huffman": 3}.get(backend, level)
    if level == 2:
        return {"zstd": 6, "zlib": 6, "lzma": 3, "huffman": 6}.get(backend, level)
    if level == 3:
        return {"zstd": 19, "zlib": 9, "lzma": 9, "huffman": 19}.get(backend, level)
    if level == 4:
        return {"zstd": 22, "zlib": 9, "lzma": 9, "huffman": 22}.get(backend, level)
    if backend == "zlib":
        return max(0, min(9, level))
    if backend == "lzma":
        return max(0, min(9, level))
    return level

def compress(data: bytes, level: int = 3, block_size: int = 65536, use_dict: bool = False, backend: "Backend" = "zstd", fast: bool = False) -> bytes:
    """Compress bytes to a .rissa container (v3 layout).

    Args:
        data: input bytes, any length.
        level: portable 1-4 (fast to max) mapped per backend
            (zstd 3/6/19/22, zlib 1/6/9/9, lzma 0/3/9/9);
            other ints pass through (clamped to 0-9 for zlib/lzma).
        block_size: split granularity (4096, 16384, 65536, 131072).
        backend: "zstd" (default) | "lzma" | "zlib" | "huffman".
        use_dict: shared 1MB->64KB dict, MDL-gated (auto-disabled when useless).
        fast: zstd-1 screen + top-4/RAW full encode; identical winners, ~3x faster.

    Returns:
        Container bytes. Raises ValueError for unknown backends.
    """
    from deep_compress.compressor_v3 import compress_with_dict
    lvl = _map_level(level, backend)
    comp, _, _ = compress_with_dict(data, backend=backend, level=lvl, block_size=block_size, use_dict=use_dict, fast=fast)
    return comp

def decompress(data: bytes, max_output_size: int | None = None) -> bytes:
    """Decompress a .rissa container of any version (v2/v3/v4 dispatch).

    max_output_size (optional, 4.6.6): total decoded-size ceiling in bytes.
    Raises:
        TruncatedError: file ends mid-field (never partial output).
        FormatError: bad magic/version/ids or cross-format feeds.
        OutputLimitError (4.6.6): a block would decode past its per-block
            guard, or the stream exceeds max_output_size. Runtime guard only;
            no valid stream can hit it.
    """
    # Dispatch on container version: v4 layout differs (8B dict header), so a
    # single decoder would misread the other version. Legacy magics go to v3
    # (which delegates DCM2/v2 internally).
    if len(data) >= 5 and data[:4] == b"RISA" and data[4] == 4:
        try:
            from deep_compress.compressor_v4 import decompress_v4
        except ImportError:
            from compressor_v4 import decompress_v4
        return decompress_v4(data, max_output_size=max_output_size)
    from deep_compress.compressor_v3 import decompress_with_dict
    return decompress_with_dict(data, max_output_size=max_output_size)

__all__ = ["compress", "decompress"]
