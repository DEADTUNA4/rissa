"""
Compressor v3: Phase 1 Architecture Upgrades
- Block size 64KB/128KB (was 16KB)
- Streaming Frame API: for block in stream (no whole-file RAM)
- Shared Dictionary Pass: 1MB sample -> 64KB header dict (zstd train or frequent substrings fallback)
"""
import struct, os
try:
    from transforms_v2 import TRANSFORMS_V2
except ImportError:
    from .transforms_v2 import TRANSFORMS_V2
try:
    from huffman import huffman_encode_block, huffman_decode_block
except ImportError:
    from .huffman import huffman_encode_block, huffman_decode_block

BLOCK_SIZE_64K = 65536
BLOCK_SIZE_128K = 131072
MAGIC = b"RISA"  # rissa - homage to Jorma Rissanen MDL 1978
VERSION = 3
EXT = ".rissa"

def build_shared_dict(data: bytes, dict_size=65536, sample_size=1_000_000):
    """
    Shared dictionary: sample first 1MB (or random 1MB if larger) -> 64KB dict
    Uses zstandard train_dictionary if available, else frequent 6-gram fallback.
    Returns dict_bytes or None
    """
    if len(data) < 1024:
        return None
    sample = data[:sample_size] if len(data) <= sample_size else data[:sample_size]
    # Try zstd train
    try:
        import zstandard as zstd
        if hasattr(zstd, 'train_dictionary'):
            # need list of samples - split sample into ~100 pieces
            pieces = [sample[i:i+8192] for i in range(0, len(sample), 8192)]
            if len(pieces) >= 2:
                d = zstd.train_dictionary(dict_size, pieces)
                db = d.as_bytes() if hasattr(d, 'as_bytes') else bytes(d)
                if len(db) > 100:
                    return db[:dict_size]
    except Exception as e:
        pass
    # Fallback: frequent 6-grams
    try:
        from collections import Counter
        counter = Counter()
        for i in range(len(sample)-6):
            counter[sample[i:i+6]] += 1
        # most common that appear >=3
        common = [k for k,v in counter.most_common(4096) if v>=3][:2048]
        # pack as dict: join with 0 separator, truncate to dict_size
        db = b'\x00'.join(common)[:dict_size]
        return db if len(db) > 256 else None
    except:
        return None

def compress_with_dict(data: bytes, backend="zstd", level=19, block_size=BLOCK_SIZE_64K, use_dict=True):
    """
    Per-block MDL + shared dict header. Dict is stored once in file header and used for all blocks via zstd dict.
    Returns (compressed_bytes, hist, dict_bytes)
    """
    import lzma, zlib
    try:
        import zstandard as zstd
        has_zstd=True
    except:
        has_zstd=False

    if backend=="zstd" and level is None: level=19
    if backend=="lzma" and level is None: level=9
    if backend=="zlib" and level is None: level=9

    dict_bytes = build_shared_dict(data) if use_dict and has_zstd and len(data)>65536 else None
    # MDL gate dict: only keep if dict reduces total size (dict overhead 4+len)
    # We will decide after per-block evaluation - for now prepare both options
    zstd_dict = None
    if dict_bytes and has_zstd:
        try:
            zstd_dict = zstd.ZstdCompressionDict(dict_bytes)
        except: zstd_dict=None
        # quick MDL check: estimate total with vs without dict on first block sample
        # If dict doesn't save at least its own size, disable it
        if len(data) > 0:
            sample = data[:min(65536, len(data))]
            # estimate compressed sample with/without dict
            try:
                c_without = zstd.ZstdCompressor(level=level).compress(sample)
                c_with = zstd.ZstdCompressor(level=level, dict_data=zstd_dict).compress(sample) if zstd_dict else c_without
                if len(c_with) + len(dict_bytes) + 4 >= len(c_without):
                    # dict not worth it, disable
                    dict_bytes = None
                    zstd_dict = None
            except:
                pass

    n=len(data)
    blocks=[data[i:i+block_size] for i in range(0, n, block_size)] if n else [b'']
    out=bytearray()
    out.extend(MAGIC)
    out.append(VERSION)
    out.append({"huffman":0,"zlib":1,"lzma":2,"zstd":3}[backend])
    out.extend(struct.pack(">I", len(blocks)))
    out.extend(struct.pack(">I", block_size))
    # dict header
    if dict_bytes:
        out.extend(struct.pack(">I", len(dict_bytes)))
        out.extend(dict_bytes)
    else:
        out.extend(struct.pack(">I", 0))
    chosen=[]
    for block in blocks:
        best_tid=0
        best_extra=b''
        best_payload=None
        best_size=float('inf')
        best_name='RAW'
        for tid,(name,enc,dec) in TRANSFORMS_V2.items():
            if tid in [5,12] and len(block)>2048: continue
            transformed, extra = enc(block)
            if transformed is None: continue
            if backend=="huffman":
                encd, freq, pad,_ = huffman_encode_block(transformed)
                payload=(encd,freq,pad)
                size=len(encd)+512
            elif backend=="zlib":
                payload=zlib.compress(transformed, level)
                size=len(payload)
            elif backend=="lzma":
                payload=lzma.compress(transformed, preset=level)
                size=len(payload)
            elif backend=="zstd":
                if not has_zstd:
                    payload=zlib.compress(transformed,9)
                else:
                    if zstd_dict:
                        cctx=zstd.ZstdCompressor(level=level, dict_data=zstd_dict)
                    else:
                        cctx=zstd.ZstdCompressor(level=level)
                    payload=cctx.compress(transformed)
                size=len(payload)
            total=size+1+len(extra)
            if total < best_size:
                best_size=total
                best_tid, best_extra, best_payload, best_name = tid, extra, payload, name
        chosen.append(best_name)
        out.append(best_tid)
        out.append(len(best_extra))
        out.extend(struct.pack(">I", len(block)))  # 4 bytes now for 64K/128K
        if backend=="huffman":
            encd,freq,pad = best_payload
            out.append(pad)
            for f in freq: out.extend(struct.pack(">H", min(f,65535)))
            out.extend(struct.pack(">I", len(encd)))
            out.extend(best_extra)
            out.extend(encd)
        else:
            comp=best_payload
            out.extend(struct.pack(">I", len(comp)))
            out.extend(best_extra)
            out.extend(comp)
    from collections import Counter
    return bytes(out), Counter(chosen), dict_bytes

def decompress_with_dict(data: bytes):
    import lzma, zlib
    try:
        import zstandard as zstd
        has_zstd=True
    except: has_zstd=False
    if not data.startswith(MAGIC):
        # backward compat: accept old DCM2/DCM3
        if data.startswith(b"DCM2") or data.startswith(b"DCM3") or data.startswith(b"DCMP"):
            from compressor_v2 import decompress_with_backend
            return decompress_with_backend(data)
        raise ValueError(f"bad magic {data[:4]!r} expected RISA")
    pos=4
    version=data[pos]; pos+=1
    backend_id=data[pos]; pos+=1
    backend={0:"huffman",1:"zlib",2:"lzma",3:"zstd"}[backend_id]
    num_blocks=struct.unpack(">I", data[pos:pos+4])[0]; pos+=4
    block_size=struct.unpack(">I", data[pos:pos+4])[0]; pos+=4
    dict_len=struct.unpack(">I", data[pos:pos+4])[0]; pos+=4
    dict_bytes=data[pos:pos+dict_len] if dict_len else None
    pos+=dict_len if dict_len else 0
    zstd_dict=None
    if dict_bytes and has_zstd:
        try: zstd_dict=zstd.ZstdCompressionDict(dict_bytes)
        except: pass
    out=bytearray()
    for _ in range(num_blocks):
        tid=data[pos]; pos+=1
        extra_len=data[pos]; pos+=1
        orig_len=struct.unpack(">I", data[pos:pos+4])[0]; pos+=4
        _, enc_fn, dec_fn = TRANSFORMS_V2[tid]
        if backend=="huffman":
            pad=data[pos]; pos+=1
            freq=[struct.unpack(">H", data[pos+i*2:pos+i*2+2])[0] for i in range(256)]
            pos+=512
            enc_len=struct.unpack(">I", data[pos:pos+4])[0]; pos+=4
            extra=data[pos:pos+extra_len]; pos+=extra_len
            encd=data[pos:pos+enc_len]; pos+=enc_len
            transformed=huffman_decode_block(encd, freq, pad, orig_len)
            out.extend(dec_fn(transformed, extra)[:orig_len])
        else:
            comp_len=struct.unpack(">I", data[pos:pos+4])[0]; pos+=4
            extra=data[pos:pos+extra_len]; pos+=extra_len
            comp=data[pos:pos+comp_len]; pos+=comp_len
            if backend=="zlib": transformed=zlib.decompress(comp)
            elif backend=="lzma": transformed=lzma.decompress(comp)
            elif backend=="zstd":
                if not has_zstd: transformed=zlib.decompress(comp)
                else:
                    dctx=zstd.ZstdDecompressor(dict_data=zstd_dict) if zstd_dict else zstd.ZstdDecompressor()
                    transformed=dctx.decompress(comp)
            out.extend(dec_fn(transformed, extra)[:orig_len])
    return bytes(out)

# Streaming Frame API: for block in stream (no whole-file RAM)
def compress_stream(in_stream, out_stream, backend="zstd", level=19, block_size=BLOCK_SIZE_64K, use_dict=False):
    """
    Streaming: reads from in_stream (file-like) in blocks, writes frame header then per-block frames.
    Use for large files that don't fit RAM. If use_dict, first 1MB is buffered to build dict (one-pass still).
    """
    # For true streaming without dict, we can start immediately. With dict, need sample.
    if use_dict:
        # buffer first 1MB to build dict, then stream rest
        sample=in_stream.read(1_000_000)
        dict_bytes=build_shared_dict(sample) if sample else None
        # write header
        import lzma, zlib
        try:
            import zstandard as zstd
            has_zstd=True
        except: has_zstd=False
        out_stream.write(MAGIC)
        out_stream.write(bytes([VERSION]))
        out_stream.write(bytes([{"huffman":0,"zlib":1,"lzma":2,"zstd":3}[backend]]))
        # we don't know num_blocks upfront for streaming -> use 0 as placeholder for streaming frame, or write dict len then stream blocks without count?
        # Simple: write block_size and dict
        out_stream.write(struct.pack(">I", block_size))
        if dict_bytes:
            out_stream.write(struct.pack(">I", len(dict_bytes)))
            out_stream.write(dict_bytes)
        else:
            out_stream.write(struct.pack(">I", 0))
        # helper to compress one block
        zstd_dict = zstd.ZstdCompressionDict(dict_bytes) if dict_bytes and has_zstd else None
        def compress_one(block):
            best=None; best_tid=0; best_extra=b''; best_name='RAW'; best_size=float('inf')
            for tid,(name,enc,dec) in TRANSFORMS_V2.items():
                if tid in [5,12] and len(block)>2048: continue
                tr, ex = enc(block)
                if tr is None: continue
                if backend=="zstd" and has_zstd:
                    cctx=zstd.ZstdCompressor(level=level, dict_data=zstd_dict) if zstd_dict else zstd.ZstdCompressor(level=level)
                    c=cctx.compress(tr)
                elif backend=="zlib": c=zlib.compress(tr, level)
                elif backend=="lzma": c=lzma.compress(tr, preset=level)
                else:
                    from huffman import huffman_encode_block
                    c,_,_,_ = huffman_encode_block(tr)
                tot=len(c)+1+len(ex)
                if tot < best_size:
                    best_size, best, best_tid, best_extra, best_name = tot, c, tid, ex, name
            # write frame: tid, extra_len, orig_len, comp_len, extra, comp
            out_stream.write(bytes([best_tid, len(best_extra)]))
            out_stream.write(struct.pack(">I", len(block)))
            out_stream.write(struct.pack(">I", len(best)))
            out_stream.write(best_extra)
            out_stream.write(best)
            return best_name
        # compress sample in blocks
        for i in range(0, len(sample), block_size):
            compress_one(sample[i:i+block_size])
        # then stream rest
        while True:
            chunk=in_stream.read(block_size)
            if not chunk: break
            compress_one(chunk)
        # we used streaming without num_blocks; decompressor must handle streaming format - for now, we provide separate decompress_stream
        return
    else:
        # dict-less streaming with known header trick: buffer all? For simplicity without dict, we can do block-wise streaming with frame count unknown -> use 0 and rely on decompress_stream reading until EOF
        # For now fallback to compress_with_dict without dict on whole data if stream is seekable -> not true streaming. Provide simple per-block frame streaming:
        import zlib, lzma
        try:
            import zstandard as zstd
            has_zstd=True
        except: has_zstd=False
        out_stream.write(MAGIC)
        out_stream.write(bytes([VERSION, {"huffman":0,"zlib":1,"lzma":2,"zstd":3}[backend]]))
        out_stream.write(struct.pack(">I", block_size))
        out_stream.write(struct.pack(">I", 0))  # no dict
        while True:
            block=in_stream.read(block_size)
            if not block: break
            # pick best transform
            best=None; best_tid=0; best_extra=b''; best_size=float('inf')
            for tid,(name,enc,dec) in TRANSFORMS_V2.items():
                if tid in [5,12] and len(block)>2048: continue
                tr,ex=enc(block)
                if tr is None: continue
                if backend=="zstd" and has_zstd: c=zstd.ZstdCompressor(level=level).compress(tr)
                elif backend=="zlib": c=zlib.compress(tr, level)
                elif backend=="lzma": c=lzma.compress(tr, preset=level)
                else:
                    from huffman import huffman_encode_block
                    c,_,_,_=huffman_encode_block(tr)
                tot=len(c)+1+len(ex)
                if tot<best_size:
                    best_size, best, best_tid, best_extra = tot, c, tid, ex
            out_stream.write(bytes([best_tid, len(best_extra)]))
            out_stream.write(struct.pack(">I", len(block)))
            out_stream.write(struct.pack(">I", len(best)))
            out_stream.write(best_extra)
            out_stream.write(best)

def decompress_stream(in_stream, out_stream):
    import zlib, lzma
    try:
        import zstandard as zstd
        has_zstd=True
    except: has_zstd=False
    magic=in_stream.read(4)
    if magic==b"DCM2":
        # v2 fallback - not streaming
        from compressor_v2 import decompress_with_backend
        data=magic+in_stream.read()
        out_stream.write(decompress_with_backend(data))
        return
    assert magic==MAGIC
    ver=in_stream.read(1)[0]
    backend_id=in_stream.read(1)[0]
    backend={0:"huffman",1:"zlib",2:"lzma",3:"zstd"}[backend_id]
    block_size=struct.unpack(">I", in_stream.read(4))[0]
    dict_len=struct.unpack(">I", in_stream.read(4))[0]
    dict_bytes=in_stream.read(dict_len) if dict_len else None
    zstd_dict=zstd.ZstdCompressionDict(dict_bytes) if dict_bytes and has_zstd else None
    while True:
        hdr=in_stream.read(2)
        if not hdr: break
        if len(hdr)<2: break
        tid, extra_len = hdr[0], hdr[1]
        orig_len_bytes=in_stream.read(4)
        if not orig_len_bytes: break
        orig_len=struct.unpack(">I", orig_len_bytes)[0]
        comp_len=struct.unpack(">I", in_stream.read(4))[0]
        extra=in_stream.read(extra_len) if extra_len else b""
        comp=in_stream.read(comp_len)
        if not comp and comp_len!=0: break
        _, enc_fn, dec_fn = TRANSFORMS_V2[tid]
        if backend=="huffman":
            # huffman streaming not fully impl - fallback
            pass
        else:
            if backend=="zlib": tr=zlib.decompress(comp)
            elif backend=="lzma": tr=lzma.decompress(comp)
            elif backend=="zstd":
                dctx=zstd.ZstdDecompressor(dict_data=zstd_dict) if zstd_dict else zstd.ZstdDecompressor()
                tr=dctx.decompress(comp)
            out_stream.write(dec_fn(tr, extra)[:orig_len])

if __name__=="__main__":
    import io
    # test block size 64K vs 16K on dickens sample
    data=open("deep_compress/silesia/dickens","rb").read()[:500000]
    for bs in [16384, 65536, 131072]:
        comp, hist, d = compress_with_dict(data, backend='zstd', block_size=bs)
        print(f"block {bs}: {len(comp)} hist {dict(hist.most_common(2))} dict {len(d) if d else 0}")
        assert decompress_with_dict(comp)==data
    print("64K/128K OK")
    # streaming
    bio_in=io.BytesIO(data)
    bio_out=io.BytesIO()
    compress_stream(bio_in, bio_out, backend='zstd', block_size=65536, use_dict=False)
    bio_out.seek(0)
    bio_dec=io.BytesIO()
    decompress_stream(bio_out, bio_dec)
    assert bio_dec.getvalue()==data
    print("streaming OK")
    # dict
    comp,hist,d=compress_with_dict(data, backend='zstd', block_size=65536, use_dict=True)
    assert decompress_with_dict(comp)==data
    print("dict OK", len(d) if d else 0)
