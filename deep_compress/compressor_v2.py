"""
Compressor v2: Per-block MDL-gated Transform Search with expanded candidates
- 9 transforms (RAW, DELTA, XOR_DELTA, DELTA2, MTF, BWT_MTF, SHUFFLE_2/4/8)
- Per-block selection (not per-file) - key to beating general compressors
- Backends: Huffman (pure), zlib, lzma (xz), zstd
"""
import struct
try:
    from transforms_v2 import TRANSFORMS_V2
except ImportError:
    from .transforms_v2 import TRANSFORMS_V2
try:
    from huffman import huffman_encode_block, huffman_decode_block
except ImportError:
    from .huffman import huffman_encode_block, huffman_decode_block

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
    version=data[pos]; pos+=1
    backend_id=data[pos]; pos+=1
    backend={0:"huffman",1:"zlib",2:"lzma",3:"zstd"}[backend_id]
    num_blocks=struct.unpack(">I", data[pos:pos+4])[0]; pos+=4
    block_size=struct.unpack(">I", data[pos:pos+4])[0]; pos+=4
    out=bytearray()
    for _ in range(num_blocks):
        tid=data[pos]; pos+=1
        extra_len=data[pos]; pos+=1
        orig_len=struct.unpack(">H", data[pos:pos+2])[0]; pos+=2
        _, enc_fn, dec_fn = TRANSFORMS_V2[tid]
        if backend=="huffman":
            padding=data[pos]; pos+=1
            freq=[struct.unpack(">H", data[pos+i*2:pos+i*2+2])[0] for i in range(256)]
            pos+=512
            enc_len=struct.unpack(">I", data[pos:pos+4])[0]; pos+=4
            extra=data[pos:pos+extra_len]; pos+=extra_len
            encoded=data[pos:pos+enc_len]; pos+=enc_len
            transformed=huffman_decode_block(encoded, freq, padding, orig_len)
            final=dec_fn(transformed, extra)
            out.extend(final[:orig_len])
        else:
            comp_len=struct.unpack(">I", data[pos:pos+4])[0]; pos+=4
            extra=data[pos:pos+extra_len]; pos+=extra_len
            comp=data[pos:pos+comp_len]; pos+=comp_len
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
