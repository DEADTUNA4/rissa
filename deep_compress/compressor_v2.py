"""
Compressor v2: Per-block MDL-gated Transform Search with expanded candidates
- 9 transforms (RAW, DELTA, XOR_DELTA, DELTA2, MTF, BWT_MTF, SHUFFLE_2/4/8)
- Per-block selection (not per-file) - key to beating general compressors
- Backends: Huffman (pure), zlib, lzma (xz), zstd
"""
import struct
try:
    from .transforms_v2 import TRANSFORMS_V2
except ImportError:
    from transforms_v2 import TRANSFORMS_V2
try:
    from .huffman import huffman_encode_block, huffman_decode_block
except ImportError:
    from huffman import huffman_encode_block, huffman_decode_block

BLOCK_SIZE = 16384  # 16KB default for Silesia - balances transform granularity vs dict
MAGIC = b"RISA"  # rissa legacy v2 compat
VERSION = 2

def compress_block_huffman(block: bytes):
    """MDL gate with Huffman backend - returns (tid, extra, encoded, freq, padding, size)"""
    best = None
    best_size = float('inf')
    for tid, (name, enc, dec) in TRANSFORMS_V2.items():
        if tid == 5 and len(block) > 2048:  # BWT limit
            continue
        transformed, extra = enc(block)
        if transformed is None:
            continue
        encoded, freq, padding, _ = huffman_encode_block(transformed)
        # total size = 1(tid)+1(extra_len)+len(extra)+512(freq)+1(padding)+4(enc_len)+len(encoded)
        total = 1 + 1 + len(extra) + 512 + 1 + 4 + len(encoded)
        if total < best_size:
            best_size = total
            best = (tid, extra, encoded, freq, padding)
    return best, best_size

def compress_with_backend(data: bytes, backend="zstd", level=None, block_size=BLOCK_SIZE):
    """
    Generic per-block transform + backend compressor.
    backend: 'zstd','lzma','zlib','huffman'
    Returns (compressed_bytes, stats)
    """
    import lzma
    import zlib
    try:
        import zstandard as zstd
        has_zstd = True
    except:
        has_zstd = False

    if backend == "zstd" and level is None:
        level = 19
    if backend == "lzma" and level is None:
        level = 9
    if backend == "zlib" and level is None:
        level = 9

    blocks = [data[i:i+block_size] for i in range(0, len(data), block_size)] if data else [b""]
    # v2 stores ORIG_LEN as >H: refuse oversize blocks loudly (silent truncation
    # would corrupt). v2 is legacy; use v3/v4 for larger blocks.
    if any(len(b) > 65535 for b in blocks):
        raise ValueError(f"v2 format stores block length as 16-bit (max 65535B); got block_size={block_size} (use v3/v4 for larger blocks)")

    out = bytearray()
    out.extend(MAGIC)
    out.append(VERSION)
    out.append({"huffman":0,"zlib":1,"lzma":2,"zstd":3}[backend])
    out.extend(struct.pack(">I", len(blocks)))
    out.extend(struct.pack(">I", block_size))
    # per-block headers + data
    chosen = []
    for block in blocks:
        best_tid = 0
        best_extra = b""
        best_payload = None
        best_size = float('inf')
        best_name = "RAW"
        for tid, (name, enc, dec) in TRANSFORMS_V2.items():
            if tid == 5 and len(block) > 2048:
                continue
            transformed, extra = enc(block)
            if transformed is None:
                continue
            # compress transformed with backend
            if backend == "huffman":
                encoded, freq, padding, _ = huffman_encode_block(transformed)
                payload = (encoded, freq, padding)
                size = len(encoded) + 512  # freq overhead
            elif backend == "zlib":
                comp = zlib.compress(transformed, level)
                payload = comp
                size = len(comp)
            elif backend == "lzma":
                comp = lzma.compress(transformed, preset=level)
                payload = comp
                size = len(comp)
            elif backend == "zstd":
                if not has_zstd:
                    comp = zlib.compress(transformed, 9)
                else:
                    cctx = zstd.ZstdCompressor(level=level)
                    comp = cctx.compress(transformed)
                payload = comp
                size = len(comp)
            # MDL: size + transform cost (1 byte tid + extra)
            total = size + 1 + len(extra)
            if total < best_size:
                best_size = total
                best_tid = tid
                best_extra = extra
                best_payload = payload
                best_name = name
        chosen.append(best_name)
        # write block header
        out.append(best_tid)
        out.append(len(best_extra))
        out.extend(struct.pack(">H", len(block)))  # orig len
        # backend-specific header
        if backend == "huffman":
            encoded, freq, padding = best_payload
            out.append(padding)
            for f in freq:
                out.extend(struct.pack(">H", min(f,65535)))
            out.extend(struct.pack(">I", len(encoded)))
            out.extend(best_extra)
            out.extend(encoded)
        else:
            # for zlib/lzma/zstd: store comp_len then data
            comp = best_payload
            out.extend(struct.pack(">I", len(comp)))
            out.extend(best_extra)
            out.extend(comp)
    # stats
    from collections import Counter
    hist = Counter(chosen)
    return bytes(out), hist

def decompress_with_backend(data: bytes):
    import lzma, zlib
    try:
        import zstandard as zstd
        has_zstd=True
    except:
        has_zstd=False
    if not data.startswith(MAGIC):
        raise ValueError("bad magic")
    pos=4
    def _need(n, what):
        nonlocal pos
        chunk = data[pos:pos+n]
        if len(chunk) < n:
            raise EOFError(f"truncated v2 .rissa file: {what} needs {n}B at offset {pos}, file ends at {len(data)}B")
        pos += n
        return chunk
    version=_need(1, "version")[0]
    if version != 2:
        raise ValueError(f"v2 decoder got version {version} (use the matching decompressor)")
    backend_id=_need(1, "backend id")[0]
    try:
        backend={0:"huffman",1:"zlib",2:"lzma",3:"zstd"}[backend_id]
    except KeyError:
        raise ValueError(f"invalid backend id {backend_id} (expected 0-3)")
    num_blocks=struct.unpack(">I", _need(4, "block count"))[0]
    if num_blocks > 100000:
        raise ValueError(f"implausible block count {num_blocks} (file likely corrupt)")
    block_size=struct.unpack(">I", _need(4, "block size"))[0]
    out=bytearray()
    for bi in range(num_blocks):
        tid=_need(1, f"block {bi} transform id")[0]
        extra_len=_need(1, f"block {bi} extra length")[0]
        orig_len=struct.unpack(">H", _need(2, f"block {bi} orig length"))[0]
        if tid not in TRANSFORMS_V2:
            raise ValueError(f"invalid transform id {tid} in block {bi} (expected 0-19)")
        _, enc_fn, dec_fn = TRANSFORMS_V2[tid]
        if backend=="huffman":
            padding=_need(1, f"block {bi} huffman padding")[0]
            freq=[struct.unpack(">H", _need(2, f"block {bi} huffman freq {i}"))[0] for i in range(256)]
            enc_len=struct.unpack(">I", _need(4, f"block {bi} huffman payload length"))[0]
            extra=_need(extra_len, f"block {bi} extra") if extra_len else b""
            encoded=_need(enc_len, f"block {bi} huffman payload")
            transformed=huffman_decode_block(encoded, freq, padding, orig_len)
            final=dec_fn(transformed, extra)
            out.extend(final[:orig_len])
        else:
            comp_len=struct.unpack(">I", _need(4, f"block {bi} payload length"))[0]
            extra=_need(extra_len, f"block {bi} extra") if extra_len else b""
            comp=_need(comp_len, f"block {bi} payload")
            if backend=="zlib":
                transformed=zlib.decompress(comp)
            elif backend=="lzma":
                transformed=lzma.decompress(comp)
            elif backend=="zstd":
                if not has_zstd:
                    transformed=zlib.decompress(comp)
                else:
                    dctx=zstd.ZstdDecompressor()
                    transformed=dctx.decompress(comp)
            final=dec_fn(transformed, extra)
            out.extend(final[:orig_len])
    return bytes(out)

# Legacy per-block Huffman compressor for backward compat (block_size 4096)
def compress(data: bytes):
    # use huffman backend with 4096 for legacy test
    comp, _ = compress_with_backend(data, backend="huffman", block_size=4096)
    return comp

def decompress(data: bytes):
    return decompress_with_backend(data)

if __name__=="__main__":
    # self test
    for sz in [0,10,100,4096,16384]:
        import os
        d=os.urandom(sz)
        for backend in ["huffman","zlib","lzma","zstd"]:
            comp,_=compress_with_backend(d, backend=backend)
            dec=decompress_with_backend(comp)
            assert dec==d, f"{backend} {sz} fail"
    print("v2 all backends roundtrip OK")
    # test transforms benefit
    d=bytes([i%256 for i in range(5000)])
    for backend in ["zlib","zstd"]:
        comp, hist=compress_with_backend(d, backend=backend)
        print(backend, hist, len(comp))
