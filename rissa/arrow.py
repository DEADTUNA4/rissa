"""
rissa[arrow] — pyarrow integration shim.

Status: pure-Python bridge. True ``pa.Codec('rissa')`` requires the C++
``arrow::util::Codec::RegisterCodec`` patch (see ``arrow_glue.cc`` draft
and the Draft PR notes) plus a pyarrow rebuild, so it cannot be done
from this package alone. This module provides the same
``compress``/``decompress`` surface so user code is already written
against the final API::

    pip install rissa[arrow]
    from rissa.arrow import RissaCodec
    codec = RissaCodec(level=3)
    blob = codec.compress(buf)          # buf: bytes / bytearray / memoryview / pa.Buffer
    raw  = codec.decompress(blob)

Buffers are passed through as ``memoryview`` (no copy on our side);
the zero-copy Arrow-buffer -> ``c_shuffle`` pointer path is the
``arrow_glue.cc`` follow-up.
"""
from __future__ import annotations

try:
    import pyarrow as pa
    _HAS_PA = True
except ImportError:  # pragma: no cover
    pa = None  # type: ignore
    _HAS_PA = False

import rissa


class RissaCodec:
    """Drop-in shaped like ``pyarrow.Codec`` but backed by rissa."""

    name = "rissa"

    def __init__(self, level: int = 3, block_size: int = 65536):
        self.level = level
        self.block_size = block_size
        self.compression_level = level

    @staticmethod
    def is_available() -> bool:
        try:
            import rissa  # noqa: F401
            return True
        except ImportError:
            return False

    def compress(self, buf, asbytes: bool = False, memory_pool=None):
        mv = buf if isinstance(buf, (bytes, bytearray, memoryview)) else (
            buf.to_pybytes() if _HAS_PA and isinstance(buf, pa.Buffer) else bytes(buf)
        )
        out = rissa.compress(bytes(mv), level=self.level, block_size=self.block_size)
        if asbytes:
            return out
        if _HAS_PA:
            return pa.py_buffer(out)
        return out

    def decompress(self, buf, decompressed_size=None, asbytes: bool = False, memory_pool=None):
        mv = buf if isinstance(buf, (bytes, bytearray, memoryview)) else (
            buf.to_pybytes() if _HAS_PA and isinstance(buf, pa.Buffer) else bytes(buf)
        )
        out = rissa.decompress(bytes(mv))
        if asbytes:
            return out
        if _HAS_PA:
            return pa.py_buffer(out)
        return out


def register(level: int = 3) -> RissaCodec:
    """Best-effort ``pa.codec('rissa')``.

    Returns a :class:`RissaCodec`. True ``pa.Codec('rissa')`` support
    needs the ``arrow_glue.cc`` C++ patch merged into Arrow and a
    rebuilt pyarrow — tracked as a Draft PR, not claimed here.
    """
    try:
        import pyarrow as pa  # noqa: F401
        try:
            return pa.Codec("rissa")  # type: ignore[no-redef]
        except (ValueError, AttributeError):
            pass
    except ImportError:
        pass
    return RissaCodec(level=level)


__all__ = ["RissaCodec", "register"]
