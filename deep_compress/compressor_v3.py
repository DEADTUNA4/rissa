"""
Compressor v3: Phase 1 Architecture Upgrades
- Block size 64KB/128KB (was 16KB)
- Streaming Frame API: for block in stream (no whole-file RAM)
- Shared Dictionary Pass: 1MB sample -> 64KB header dict (zstd train or frequent substrings fallback)
"""
import struct, os
try:
    from .diag import note
except ImportError:
    from diag import note
try:
    from .transforms_v2 import TRANSFORMS_V2, HAS_C_TRANS
except ImportError:
    from transforms_v2 import TRANSFORMS_V2, HAS_C_TRANS
try:
    from .huffman import huffman_encode_block, huffman_decode_block
except ImportError:
    from huffman import huffman_encode_block, huffman_decode_block

BLOCK_SIZE_64K = 65536
BLOCK_SIZE_128K = 131072
MAGIC = b"RISA"  # rissa - homage to Jorma Rissanen MDL 1978
VERSION = 3
EXT = ".rissa"

# BWT-family transforms: the Python radix sort cost ~8s per 128K block, so
# fast mode used to skip them without even computing them. With C BWT active
# (HAS_C_TRANS) they cost ~0.1s and rejoin the screen; without C the skip stays.
BWT_TIDS = {5, 12, 16}

def _encode_with_backend(transformed, backend, level, has_zstd, zstd_dict):
    """Single backend encode. Returns (payload, size) with the same shapes
    as the inline loop below (huffman payload is a tuple)."""
    import lzma, zlib
    if backend == "huffman":
        encd, freq, pad, _ = huffman_encode_block(transformed)
        return (encd, freq, pad), len(encd) + 512
    elif backend == "zlib":
        comp = zlib.compress(transformed, level)
        return comp, len(comp)
    elif backend == "lzma":
        comp = lzma.compress(transformed, preset=level)
        return comp, len(comp)
    elif backend == "zstd":
        if not has_zstd:
            comp = zlib.compress(transformed, 9)
            return comp, len(comp)
        if zstd_dict:
            import zstandard as zstd
            cctx = zstd.ZstdCompressor(level=level, dict_data=zstd_dict)
        else:
            import zstandard as zstd
            cctx = zstd.ZstdCompressor(level=level)
        comp = cctx.compress(transformed)
        return comp, len(comp)
    raise ValueError(f"unknown backend {backend!r}")

def _eval_block_v3(block: bytes, backend: str, level, has_zstd: bool, zstd_dict, fast: bool):
    """Per-block MDL evaluation (fast screen + exhaustive fallback).

    Pure function of its arguments: no cross-block state, shared inputs are
    read-only. Safe to run in worker threads; same code path as the serial
    loop, so serial and parallel output is byte-identical.
    Returns (best_tid, best_extra, best_payload, best_name).
    """
    import lzma, zlib
    try:
        from .transforms_v2 import TRANSFORMS_V2
    except ImportError:
        from transforms_v2 import TRANSFORMS_V2
    try:
        from .huffman import huffman_encode_block
    except ImportError:
        from huffman import huffman_encode_block
    best_tid = 0
    best_extra = b''
    best_payload = None
    best_size = float('inf')
    best_name = 'RAW'
    # Fast path: screen with zlib-1, full-encode top-3 + RAW only.
    # BWT family rejoins the screen when C BWT is active, else still skipped.
    skip_bwt = fast and not HAS_C_TRANS
    tids = [tid for tid in TRANSFORMS_V2 if not (skip_bwt and tid in BWT_TIDS)]
    if fast and backend in ("lzma", "zstd") and tids:
        tcache = {}
        scored = []
        # Screen estimator: same-family fast level (zstd-1) predicts the true
        # backend far better than zlib-1 (56-block panel: top-3 misses 4/56
        # either way, but zstd-1 >= zlib-1 on every corpus and hits lzma-9
        # winners zlib-1 misses). Falls back to zlib-1 without zstandard.
        zc1 = None
        if has_zstd:
            try:
                import zstandard as _zstd
                zc1 = _zstd.ZstdCompressor(level=1)
            except Exception as e:
                note("v3-screen zstd-1 setup", e)
                zc1 = None
        for tid in tids:
            name, enc, dec = TRANSFORMS_V2[tid]
            if tid in [5, 12] and len(block) > 2048: continue
            try:
                transformed, extra = enc(block)
            except Exception as e:
                note(f"v3-screen {name}", e)
                continue
            if transformed is None: continue
            tcache[tid] = (transformed, extra)
            try:
                if zc1 is not None:
                    screen = len(zc1.compress(transformed)) + 1 + len(extra)
                else:
                    screen = len(zlib.compress(transformed, 1)) + 1 + len(extra)
            except Exception as e:
                note(f"v3-screen estimate {name}", e)
                continue
            scored.append((screen, tid))
        if scored:
            scored.sort(key=lambda t: (t[0], t[1]))
            # Top-4 (was top-3): panel misses drop 4/56 -> 2/56 (xml only),
            # one extra full encode per block for measurably better winners.
            keep = {tid for _, tid in scored[:4]} | ({0} if 0 in tcache else set())
            for tid in tids:
                if tid not in keep: continue
                name, enc, dec = TRANSFORMS_V2[tid]
                transformed, extra = tcache[tid]
                try:
                    payload, size = _encode_with_backend(transformed, backend, level, has_zstd, zstd_dict)
                except Exception as e:
                    note(f"v3-backend {name}/{backend}", e)
                    continue
                total = size + 1 + len(extra)
                if total < best_size:
                    best_size = total
                    best_tid, best_extra, best_payload, best_name = tid, extra, payload, name
        else:
            pass  # screen found nothing usable; fall through to exhaustive
    if best_payload is None:
        # Exhaustive path (default; also fallback when screening yields nothing).
        # NOTE: duplicated rather than refactored so default behavior is byte-identical.
        for tid, (name, enc, dec) in TRANSFORMS_V2.items():
            if tid in [5, 12] and len(block) > 2048: continue
            transformed, extra = enc(block)
            if transformed is None: continue
            if backend == "huffman":
                encd, freq, pad, _ = huffman_encode_block(transformed)
                payload = (encd, freq, pad)
                size = len(encd) + 512
            elif backend == "zlib":
                payload = zlib.compress(transformed, level)
                size = len(payload)
            elif backend == "lzma":
                payload = lzma.compress(transformed, preset=level)
                size = len(payload)
            elif backend == "zstd":
                if not has_zstd:
                    payload = zlib.compress(transformed, 9)
                else:
                    if zstd_dict:
                        import zstandard as zstd
                        cctx = zstd.ZstdCompressor(level=level, dict_data=zstd_dict)
                    else:
                        import zstandard as zstd
                        cctx = zstd.ZstdCompressor(level=level)
                    payload = cctx.compress(transformed)
                size = len(payload)
            total = size + 1 + len(extra)
            if total < best_size:
                best_size = total
                best_tid, best_extra, best_payload, best_name = tid, extra, payload, name
    return best_tid, best_extra, best_payload, best_name

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
    # Fallback: frequent 6-grams (C rank_ngrams matches Counter.most_common order)
    try:
        import rissa.c_stat as _CS
        common = _CS.rank_ngrams(bytes(sample), 6, 3, 4096)[:2048]
    except Exception as e:
        note("shared-dict ngrams", e)
        try:
            from collections import Counter
            counter = Counter()
            for i in range(len(sample)-6):
                counter[sample[i:i+6]] += 1
            # most common that appear >=3
            common = [k for k,v in counter.most_common(4096) if v>=3][:2048]
        except Exception as e2:
            note("shared-dict counter", e2)
            return None
    try:
        # pack as dict: join with 0 separator, truncate to dict_size
        db = b'\x00'.join(common)[:dict_size]
        return db if len(db) > 256 else None
    except Exception as e:
        note("shared-dict pack", e)
        return None

def compress_with_dict(data: bytes, backend="zstd", level=19, block_size=BLOCK_SIZE_64K, use_dict=True, fast=False, max_workers=None):
    """
    Per-block MDL + shared dict header. Dict is stored once in file header and used for all blocks via zstd dict.
    Returns (compressed_bytes, hist, dict_bytes)
    fast=True: two-stage MDL (zstd-1 screen -> full encode of top-4 + RAW) and
    skip BWT-family transform computation. ~10x faster on structured data;
    winners verified identical on sensor/columnar samples. Default False keeps
    exhaustive search (published benchmark numbers).
    max_workers: None = auto (6 threads when >4 blocks, else serial);
    1 = forced serial; N = forced N threads. Parallel output is byte-identical
    (ordered reassembly, same per-block function).
    """
    import lzma, zlib
    try:
        import zstandard as zstd
        has_zstd=True
    except Exception:
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
        except Exception as e:
            note("v3 zstd dict compile", e)
            zstd_dict=None
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
            except Exception as e:
                note("v3 dict MDL gate", e)
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
    # Per-block evaluation: serial or ThreadPool (blocks independent, shared
    # inputs read-only; backends release the GIL, so threads scale).
    if max_workers is None:
        workers = 6 if len(blocks) > 4 else 1
    else:
        workers = max(1, max_workers)
    if workers > 1 and len(blocks) > 1:
        import concurrent.futures as _cf
        import functools as _ft
        _eval = _ft.partial(_eval_block_v3, backend=backend, level=level,
                            has_zstd=has_zstd, zstd_dict=zstd_dict, fast=fast)
        with _cf.ThreadPoolExecutor(max_workers=min(workers, len(blocks))) as _ex:
            results = list(_ex.map(_eval, blocks))
    else:
        results = [_eval_block_v3(b, backend, level, has_zstd, zstd_dict, fast) for b in blocks]
    for block, (best_tid, best_extra, best_payload, best_name) in zip(blocks, results):
        if len(best_extra) > 255:
            raise ValueError(f"transform extra {len(best_extra)}B exceeds 1-byte EXTRA_LEN field (tid {best_tid})")
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
            try:
                from .compressor_v2 import decompress_with_backend
            except ImportError:
                from deep_compress.compressor_v2 import decompress_with_backend
            return decompress_with_backend(data)
        raise ValueError(f"bad magic {data[:4]!r} expected RISA")
    pos=4
    def _need(n, what):
        nonlocal pos
        chunk = data[pos:pos+n]
        if len(chunk) < n:
            raise EOFError(f"truncated .rissa file: {what} needs {n}B at offset {pos}, file ends at {len(data)}B")
        pos += n
        return chunk
    version=_need(1, "version")[0]
    if version == 2:
        # v2 layout differs (16-bit orig_len): delegate, don't misread as v3.
        try:
            from .compressor_v2 import decompress_with_backend
        except ImportError:
            from deep_compress.compressor_v2 import decompress_with_backend
        return decompress_with_backend(data)
    if version == 4:
        raise ValueError("v4 .rissa frame: use decompress_v4(), not decompress_with_dict()")
    if version != 3:
        raise ValueError(f"unsupported .rissa version {version} (expected 2, 3 or 4)")
    backend_id=_need(1, "backend id")[0]
    try:
        backend={0:"huffman",1:"zlib",2:"lzma",3:"zstd"}[backend_id]
    except KeyError:
        raise ValueError(f"invalid backend id {backend_id} (expected 0-3)")
    num_blocks=struct.unpack(">I", _need(4, "block count"))[0]
    if num_blocks == STREAM_SENTINEL:
        raise ValueError("streaming .rissa frame: use decompress_stream(), not decompress_with_dict()")
    if num_blocks > 100000:
        raise ValueError(f"implausible block count {num_blocks} (file likely corrupt)")
    block_size=struct.unpack(">I", _need(4, "block size"))[0]
    dict_len=struct.unpack(">I", _need(4, "dict length"))[0]
    dict_bytes=_need(dict_len, "dict") if dict_len else None
    zstd_dict=None
    if dict_bytes and has_zstd:
        try: zstd_dict=zstd.ZstdCompressionDict(dict_bytes)
        except: pass
    out=bytearray()
    for bi in range(num_blocks):
        tid=_need(1, f"block {bi} transform id")[0]
        extra_len=_need(1, f"block {bi} extra length")[0]
        orig_len=struct.unpack(">I", _need(4, f"block {bi} orig length"))[0]
        if tid not in TRANSFORMS_V2:
            raise ValueError(f"invalid transform id {tid} in block {bi} (expected 0-19)")
        _, enc_fn, dec_fn = TRANSFORMS_V2[tid]
        if backend=="huffman":
            pad=_need(1, f"block {bi} huffman padding")[0]
            freq=[struct.unpack(">H", _need(2, f"block {bi} huffman freq {i}"))[0] for i in range(256)]
            enc_len=struct.unpack(">I", _need(4, f"block {bi} huffman payload length"))[0]
            extra=_need(extra_len, f"block {bi} extra") if extra_len else b""
            encd=_need(enc_len, f"block {bi} huffman payload")
            transformed=huffman_decode_block(encd, freq, pad, orig_len)
            out.extend(dec_fn(transformed, extra)[:orig_len])
        else:
            comp_len=struct.unpack(">I", _need(4, f"block {bi} payload length"))[0]
            extra=_need(extra_len, f"block {bi} extra") if extra_len else b""
            comp=_need(comp_len, f"block {bi} payload")
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
STREAM_SENTINEL = 0xFFFFFFFF  # num_blocks slot value marking a streaming frame (FORMAT.md)

def compress_stream(in_stream, out_stream, backend="zstd", level=19, block_size=BLOCK_SIZE_64K, use_dict=False):
    """
    Streaming: reads from in_stream (file-like) in blocks, writes frame header then per-block frames.
    Use for large files that don't fit RAM. If use_dict, first 1MB is buffered to build dict (one-pass still).
    Header carries STREAM_SENTINEL in the num_blocks slot so the normal
    decoder can reject streaming frames with a clean error instead of misdecoding.
    huffman backend is REFUSED (stream frames have no frequency-table field;
    added a clear ValueError rather than writing undecodable frames).
    """
    if backend == "huffman":
        raise ValueError("huffman backend is not supported for streaming: stream frames carry no frequency table (use zstd/lzma/zlib)")
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
        out_stream.write(struct.pack(">I", STREAM_SENTINEL))  # streaming frame marker
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
                    try:
                        from .huffman import huffman_encode_block
                    except ImportError:
                        from deep_compress.huffman import huffman_encode_block
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
        out_stream.write(struct.pack(">I", STREAM_SENTINEL))  # streaming frame marker
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
                    try:
                        from .huffman import huffman_encode_block
                    except ImportError:
                        from deep_compress.huffman import huffman_encode_block
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
        try:
            from .compressor_v2 import decompress_with_backend
        except ImportError:
            from deep_compress.compressor_v2 import decompress_with_backend
        data=magic+in_stream.read()
        out_stream.write(decompress_with_backend(data))
        return
    assert magic==MAGIC
    def _sread(n, what):
        chunk = in_stream.read(n)
        if len(chunk) < n:
            raise EOFError(f"truncated streaming .rissa file: {what} needs {n}B, stream ended")
        return chunk
    ver=_sread(1, "version")[0]
    if ver not in (3, 4):
        raise ValueError(f"unsupported streaming version {ver} (expected 3 or 4)")
    backend_id=_sread(1, "backend id")[0]
    try:
        backend={0:"huffman",1:"zlib",2:"lzma",3:"zstd"}[backend_id]
    except KeyError:
        raise ValueError(f"invalid backend id {backend_id} in streaming header")
    if backend == "huffman":
        raise ValueError("huffman streaming frames are not decodable (no frequency table was stored); file was written by a pre-fix writer")
    first=struct.unpack(">I", _sread(4, "block size / sentinel"))[0]
    if first == STREAM_SENTINEL:
        block_size=struct.unpack(">I", _sread(4, "block size"))[0]
    else:
        block_size=first  # legacy stream files (pre-sentinel): block size sits here
    dict_len=struct.unpack(">I", _sread(4, "dict length"))[0]
    dict_bytes=_sread(dict_len, "dict") if dict_len else None
    zstd_dict=zstd.ZstdCompressionDict(dict_bytes) if dict_bytes and has_zstd else None
    nblocks_out = 0
    while True:
        hdr=in_stream.read(2)
        if not hdr:
            break  # clean EOF between frames: normal end of stream
        if len(hdr)<2:
            raise EOFError("truncated streaming .rissa file: 2B frame header cut short")
        tid, extra_len = hdr[0], hdr[1]
        if tid not in TRANSFORMS_V2:
            raise ValueError(f"invalid transform id {tid} in stream at block {nblocks_out}")
        orig_len=struct.unpack(">I", _sread(4, "frame orig length"))[0]
        comp_len=struct.unpack(">I", _sread(4, "frame comp length"))[0]
        extra=_sread(extra_len, "frame extra") if extra_len else b""
        comp=_sread(comp_len, "frame payload")
        _, enc_fn, dec_fn = TRANSFORMS_V2[tid]
        if backend=="zlib": tr=zlib.decompress(comp)
        elif backend=="lzma": tr=lzma.decompress(comp)
        elif backend=="zstd":
            dctx=zstd.ZstdDecompressor(dict_data=zstd_dict) if zstd_dict else zstd.ZstdDecompressor()
            tr=dctx.decompress(comp)
        out_stream.write(dec_fn(tr, extra)[:orig_len])
        nblocks_out += 1

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
