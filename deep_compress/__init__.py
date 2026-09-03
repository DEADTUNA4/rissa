"""rissa - https://rissa.web.app"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from .compressor_v3 import compress_with_dict, decompress_with_dict

def compress(data: bytes, level: int = 3, **kw):
    lvl = {1:3, 2:6, 3:19, 4:22}.get(level, level)
    comp, _, _ = compress_with_dict(data, level=lvl, **kw)
    return comp

def decompress(data: bytes):
    return decompress_with_dict(data)
