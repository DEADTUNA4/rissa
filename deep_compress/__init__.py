"""rissa v4.3 - https://rissa.web.app"""
__version__ = "4.6.3"
import sys, os
_p = os.path.normpath(os.path.dirname(os.path.abspath(__file__)))
if _p not in sys.path:
    sys.path.insert(0, _p)
del _p
from .compressor_v3 import compress_with_dict, decompress_with_dict
try:
    from .compressor_v4 import compress_v4, decompress_v4
except: pass

def compress(data: bytes, level: int = 3, **kw):
    lvl = {1:3, 2:6, 3:19, 4:22}.get(level, level)
    comp, _, _ = compress_with_dict(data, level=lvl, **kw)
    return comp

def decompress(data: bytes):
    if len(data) >= 5 and data[:4] == b"RISA" and data[4] == 4:
        try:
            from .compressor_v4 import decompress_v4
            return decompress_v4(data)
        except ImportError:
            pass
    return decompress_with_dict(data)
