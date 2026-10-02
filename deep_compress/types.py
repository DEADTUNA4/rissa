"""Shared public types for rissa.

Kept in one place so the public API, the engines, and user code all mean
the same thing. Python 3.9 floor: no `slots=True` (3.10+), no runtime
`X | Y` without `from __future__ import annotations` (used below).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union

#: Entropy backends selectable by name. Anything else raises ValueError early.
Backend = Literal["zstd", "lzma", "zlib", "huffman"]


@dataclass
class BlockResult:
    """One block's MDL decision.

    Attributes:
        transform_id: registry id written as the block's TID byte.
        extra: side info (BWT primary, shuffle stride, ...) counted in MDL.
        payload: backend-encoded bytes; for the huffman backend a
            `(encoded, freq, padding)` tuple instead (same shape the entropy
            coder returns).
        transform_name: human-readable winner, e.g. "SHUFFLE_4".
    """

    transform_id: int
    extra: bytes
    payload: Union[bytes, tuple]
    transform_name: str
