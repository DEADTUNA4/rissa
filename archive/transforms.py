"""
Layer 1: Reversible Transform Search
Theory: redundancy is hidden by representation. Find T that minimizes entropy.
"""
import struct

def delta_encode(data: bytes) -> bytes:
    if not data:
        return b""
    out = bytearray(len(data))
    out[0]=data[0]
    for i in range(1,len(data)):
        out[i] = (data[i] - data[i-1]) & 0xFF
    return bytes(out)

def delta_decode(data: bytes) -> bytes:
    if not data:
        return b""
    out = bytearray(len(data))
    out[0]=data[0]
    for i in range(1,len(data)):
        out[i] = (data[i] + out[i-1]) & 0xFF
    return bytes(out)

def xor_encode(data: bytes) -> bytes:
    if not data:
        return b""
    out = bytearray(len(data))
    out[0]=data[0]
    for i in range(1,len(data)):
        out[i] = data[i] ^ data[i-1]
    return bytes(out)

def xor_decode(data: bytes) -> bytes:
    if not data:
        return b""
    out = bytearray(len(data))
    out[0]=data[0]
    for i in range(1,len(data)):
        out[i] = data[i] ^ out[i-1]
    return bytes(out)

def bwt_encode(data: bytes):
    """Burrows-Wheeler Transform - exposes sorted context. Returns (bwt_data, primary_index)"""
    n = len(data)
    if n==0:
        return b"", 0
    # naive O(n^2 log n) - limit to 4096 for experiment
    if n>4096:
        return None, None
    # Use memory efficient sort with key: we can use sorted indices
    # Python's sorted with slicing is heavy but ok for small n
    rotations = [data[i:]+data[:i] for i in range(n)]
    # Instead of storing rotations, sort indices via tuple comparison
    # For speed, use python's sorted on bytes
    sorted_rots = sorted(rotations)
    # Find primary index: where original data appears
    try:
        primary = sorted_rots.index(data)
    except:
        primary = 0
    bwt = bytes(r[-1] for r in sorted_rots)
    return bwt, primary

def bwt_decode(bwt_data: bytes, primary: int) -> bytes:
    n = len(bwt_data)
    if n==0:
        return b""
    # inverse BWT via LF mapping
    # Standard method: table method
    table = [""]*n
    for _ in range(n):
        table = sorted([bwt_data[i] + table[i] for i in range(n)])
    return table[primary].encode('latin1') if isinstance(table[primary], str) else table[primary]

# Faster inverse using counting sort LF
def bwt_decode_fast(bwt: bytes, primary: int) -> bytes:
    n = len(bwt)
    if n==0:
        return b""
    # Count occurrences
    # Build LF mapping
    # 1. Count chars
    counts = [0]*256
    for c in bwt:
        counts[c]+=1
    # 2. Start positions in sorted order
    starts = [0]*256
    sum_ = 0
    for i in range(256):
        starts[i]=sum_
        sum_+=counts[i]
    # 3. Build occ ranks
    occ = [0]*n
    cur = [0]*256
    for i, c in enumerate(bwt):
        occ[i]=cur[c]
        cur[c]+=1
    # 4. LF
    res = bytearray(n)
    row = primary
    for i in range(n-1, -1, -1):
        res[i]=bwt[row]
        c = bwt[row]
        row = starts[c] + occ[row]
    return bytes(res)

def mtf_encode(data: bytes) -> bytes:
    """Move-To-Front - makes BWT output highly compressible (many zeros)"""
    alphabet = list(range(256))
    out = bytearray()
    for c in data:
        idx = alphabet.index(c)
        out.append(idx)
        # move to front
        alphabet.pop(idx)
        alphabet.insert(0, c)
    return bytes(out)

def mtf_decode(data: bytes) -> bytes:
    alphabet = list(range(256))
    out = bytearray()
    for idx in data:
        c = alphabet[idx]
        out.append(c)
        alphabet.pop(idx)
        alphabet.insert(0, c)
    return bytes(out)

# Transform registry: id -> (name, encode, decode, needs_extra)
TRANSFORMS = {
    0: ("RAW", lambda x: (x, b""), lambda x, e: x),
    1: ("DELTA", lambda x: (delta_encode(x), b""), lambda x, e: delta_decode(x)),
    2: ("XOR", lambda x: (xor_encode(x), b""), lambda x, e: xor_decode(x)),
    3: ("BWT_MTF", lambda x: _bwt_mtf_encode(x), lambda x, e: _bwt_mtf_decode(x, e)),
}

def _bwt_mtf_encode(data: bytes):
    bwt, primary = bwt_encode(data)
    if bwt is None:
        return None, None
    mtf = mtf_encode(bwt)
    extra = struct.pack(">H", primary)  # 2 bytes for primary index (max 4096)
    return mtf, extra

def _bwt_mtf_decode(data: bytes, extra: bytes):
    primary = struct.unpack(">H", extra)[0] if extra else 0
    bwt = mtf_decode(data)
    return bwt_decode_fast(bwt, primary)

def list_transforms():
    return TRANSFORMS
