"""
rissa — https://rissa.web.app
import rissa; rissa.compress(data, level=3)
"""
__version__ = "4.5.0"
__author__ = "rissa (Rissanen MDL 1978) v4.3"
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "deep_compress"))
from deep_compress.compressor_v3 import compress_with_dict, decompress_with_dict

def compress(data: bytes, level: int = 3, block_size: int = 65536, use_dict: bool = False, backend: str = "zstd") -> bytes:
    lvl = {1:3, 2:6, 3:19, 4:22}.get(level, level)
    comp, _, _ = compress_with_dict(data, backend=backend, level=lvl, block_size=block_size, use_dict=use_dict)
    return comp

def decompress(data: bytes) -> bytes:
    return decompress_with_dict(data)

__all__ = ["compress", "decompress"]
