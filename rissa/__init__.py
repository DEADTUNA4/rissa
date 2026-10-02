"""
rissa - https://rissa.web.app
import rissa; rissa.compress(data, level=3)

Public API (stable): compress() writes the v3 container; decompress() reads
any version (v2/v3/v4 dispatch). Containers: v3 default, v4 opt-in via
deep_compress.compressor_v4. Internals: deep_compress.* (escape hatches).
"""
__version__ = "4.6.4"
__author__ = "rissa (Rissanen MDL 1978) v4.3"
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

def compress(data: bytes, level: int = 3, block_size: int = 65536, use_dict: bool = False, backend: "Backend" = "zstd", fast: bool = False) -> bytes:
    """Compress bytes to a .rissa container (v3 layout).

    Args:
        data: input bytes, any length.
        level: 1->3, 2->6, 3->19, 4->22 (backend levels); other ints pass through.
        block_size: split granularity (4096, 16384, 65536, 131072).
        backend: "zstd" (default) | "lzma" | "zlib" | "huffman".
        use_dict: shared 1MB->64KB dict, MDL-gated (auto-disabled when useless).
        fast: zstd-1 screen + top-4/RAW full encode; identical winners, ~3x faster.

    Returns:
        Container bytes. Raises ValueError for unknown backends.
    """
    from deep_compress.compressor_v3 import compress_with_dict
    lvl = {1:3, 2:6, 3:19, 4:22}.get(level, level)
    comp, _, _ = compress_with_dict(data, backend=backend, level=lvl, block_size=block_size, use_dict=use_dict, fast=fast)
    return comp

def decompress(data: bytes) -> bytes:
    """Decompress a .rissa container of any version (v2/v3/v4 dispatch).

    Raises:
        TruncatedError: file ends mid-field (never partial output).
        FormatError: bad magic/version/ids or cross-format feeds.
    """
    # Dispatch on container version: v4 layout differs (8B dict header), so a
    # single decoder would misread the other version. Legacy magics go to v3
    # (which delegates DCM2/v2 internally).
    if len(data) >= 5 and data[:4] == b"RISA" and data[4] == 4:
        try:
            from deep_compress.compressor_v4 import decompress_v4
        except ImportError:
            from compressor_v4 import decompress_v4
        return decompress_v4(data)
    from deep_compress.compressor_v3 import decompress_with_dict
    return decompress_with_dict(data)

__all__ = ["compress", "decompress"]
