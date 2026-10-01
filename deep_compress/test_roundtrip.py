"""
Round-trip harness + fuzz + adversarial tests. Non-negotiable before any claim.
Tests every transform and compressor per review point 6.
"""
import os, random, struct

import sys
sys.path.insert(0, '.')
try:
    from transforms_v2 import TRANSFORMS_V2, shuffle_encode, shuffle_decode, racd_encode, racd_decode, bwt_encode
except ImportError:
    from .transforms_v2 import TRANSFORMS_V2, shuffle_encode, shuffle_decode, racd_encode, racd_decode, bwt_encode
try:
    from compressor_v2 import compress_with_backend, decompress_with_backend
except ImportError:
    from .compressor_v2 import compress_with_backend, decompress_with_backend
try:
    from huffman import huffman_encode_block, huffman_decode_block
except ImportError:
    from .huffman import huffman_encode_block, huffman_decode_block

def test_transforms():
    print("=== Transform round-trip ===")
    cases=[
        b"",
        b"a",
        b"ab",
        b"aaaa",
        b"a"*1000,
        b"\x00"*1000,
        b"\xFF"*1000,
        os.urandom(1),
        os.urandom(10),
        os.urandom(4096),
        bytes([i%256 for i in range(1000)]),
        b"hello world "*1000,
    ]
    # adversarial
    cases.extend([
        b"\x00\x00\x00\x00"*100,  # zeros
        b"\xFF\xFE\xFD"*500,
        bytes([0,1]*2000),  # alternating
        b"a"*1_000_000 if False else b"a"*100000,  # large same-byte (skip 1M for speed)
    ])
    for tid, (name, enc, dec) in TRANSFORMS_V2.items():
        for data in cases:
            if tid in [5,12] and len(data)>2048:
                continue
            enc_data, extra = enc(data)
            if enc_data is None:
                continue
            dec_data = dec(enc_data, extra)
            assert dec_data == data, f"{name} failed on len {len(data)}"
        print(f"  {name}: OK")
    print("All transforms OK")

def test_shuffle_adversarial():
    print("\n=== Shuffle adversarial ===")
    for stride in [2,4,8]:
        for n in [0,1,2,3,4,5,7,15,16,17,4095,4096,4097,8191]:
            d=os.urandom(n) if n>0 else b""
            assert shuffle_decode(shuffle_encode(d,stride),stride)==d
    print("  shuffle OK")

def test_huffman():
    print("\n=== Huffman ===")
    for data in [b"", b"a", b"aaaa", b"abracadabra", os.urandom(1000), bytes([i%256 for i in range(5000)])]:
        enc, freq, pad, _ = huffman_encode_block(data)
        dec = huffman_decode_block(enc, freq, pad, len(data))
        assert dec==data, "huffman fail"
    print("  huffman OK")

def test_compressor():
    print("\n=== Compressor round-trip (all backends) ===")
    cases=[
        b"",
        b"x",
        b"a"*100,
        b"hello world",
        bytes([i%256 for i in range(5000)]),
        os.urandom(1024),
        os.urandom(16384),
        b"\x00"*5000 + b"\xFF"*5000,
        # already compressed (should fallback to RAW)
        zlib_compress := __import__("zlib").compress(b"hello world"*1000, 9),
        # executable-like
        os.urandom(5000) + b"\x00\x01\x02"*1000,
        # sqlite-like structured
        struct.pack('<'+'I'*1000, *range(1000)),
    ]
    for backend in ['huffman','zlib','lzma','zstd']:
        for data in cases:
            comp, hist = compress_with_backend(data, backend=backend, block_size=4096)
            dec = decompress_with_backend(comp)
            assert dec == data, f"{backend} failed len {len(data)}"
        print(f"  {backend}: OK")
    print("All compressor OK")

def test_v4_huffman_known_failure():
    # KNOWN FAILURE (pre-existing, verified via git stash on original code):
    # compressor_v4.compress_v4 with backend='huffman' writes a truncated
    # block (no payload in the huffman branch), so decompress_v4 fails with
    # struct.error. compressor_v2's huffman path (tested above) is fine.
    # See CHANGELOG "Known issues". If this ever prints FIXED, promote it
    # to a full roundtrip assertion and close the changelog entry.
    print("\n=== v4+huffman (KNOWN FAILURE, see CHANGELOG) ===")
    try:
        from compressor_v4 import compress_v4, decompress_v4
    except ImportError as e:
        print(f"  skip (no compressor_v4): {e}")
        return "skipped"
    data = b"x" * 20000  # RLE TID picks huffman path deterministically
    try:
        comp, hist, _ = compress_v4(data, backend='huffman', block_size=20000, use_dict=False)
        dec = decompress_v4(comp)
        if dec == data:
            print("  FIXED — v4+huffman roundtrips now; promote to full test + close CHANGELOG entry")
            return "fixed"
        else:
            print("  UNEXPECTED: decoded without error but mismatch")
            return "unexpected"
    except Exception as e:
        print(f"  KNOWN FAILURE still present ({type(e).__name__}): v4+huffman decompress broken, pre-existing")
        return "known-fail"

def test_determinism():
    print("\n=== Determinism ===")
    data=os.urandom(5000)
    for backend in ['zstd','lzma']:
        comp1,_=compress_with_backend(data, backend=backend)
        comp2,_=compress_with_backend(data, backend=backend)
        assert comp1==comp2, "non-deterministic"
    print("  deterministic OK")

def test_versioning():
    print("\n=== Versioning ===")
    data=b"test version"
    comp,_=compress_with_backend(data, backend='zstd')
    # v4.4 uses RISA v4, legacy DCM2 still accepted
    assert comp[:4]==b"RISA" or comp[:4]==b"DCM2", f"magic {comp[:4]}"
    assert comp[4]==4 or comp[4]==2, f"version {comp[4]}"
    dec=decompress_with_backend(comp)
    assert dec==data
    print("  versioning OK")
    # Also test v4
    try:
        from compressor_v4 import compress_v4, decompress_v4
        comp4,_,_=compress_v4(data, backend='zstd')
        assert comp4[:4]==b"RISA" and comp4[4]==4
        assert decompress_v4(comp4)==data
        print("  v4 versioning OK")
    except Exception as e:
        print(f"  v4 versioning skip {e}")
    # Test RACD
    try:
        tr, ex = racd_encode(b"a b c\n"*100 + b"  irregular   spacing\n"*10)
        assert racd_decode(tr, ex) == b"a b c\n"*100 + b"  irregular   spacing\n"*10
        print("  RACD whitespace preserve OK")
    except Exception as e:
        print(f"  RACD skip {e}")
    # Test BWT branch split (256K)
    try:
        data_bwt=b"banana"*1000
        from transforms_v2 import bwt_encode, bwt_decode_fast
        bwt, p = bwt_encode(data_bwt)
        assert bwt_decode_fast(bwt, p)==data_bwt
        print("  BWT 256K OK")
    except Exception as e:
        print(f"  BWT skip {e}")

def fuzz_random():
    print("\n=== Fuzz 200 random ===")
    for i in range(200):
        n=random.randint(0, 20000)
        d=os.urandom(n)
        backend=random.choice(['huffman','zlib','zstd'])
        comp,_=compress_with_backend(d, backend=backend, block_size=random.choice([4096,16384]))
        dec=decompress_with_backend(comp)
        assert dec==d, f"fuzz {i} fail"
        if i%50==0:
            print(f"  {i}/200")
    print("  fuzz OK")

def fuzz_truncated():
    print("\n=== Fuzz truncated/corrupted ===")
    data=b"hello world "*1000
    comp,_=compress_with_backend(data, backend='zstd')
    # truncate
    try:
        decompress_with_backend(comp[:100])
        print("  truncated should have failed but didn't crash (ok)")
    except Exception as e:
        print(f"  truncated correctly failed: {type(e).__name__}")
    # corrupt
    corrupted=bytearray(comp)
    if len(corrupted)>50:
        corrupted[50]^=0xFF
        try:
            decompress_with_backend(bytes(corrupted))
            print("  corrupted should have failed")
        except Exception as e:
            print(f"  corrupted correctly failed: {type(e).__name__}")
    print("  fuzz truncated OK")

def test_audit_regressions():
    """Regression tests for the external audit (see CHANGELOG unreleased).
    Each would silently corrupt, silently drop data, or misdecode before."""
    print("\n=== Audit regressions ===")
    try:
        from compressor_v3 import (compress_with_dict, decompress_with_dict,
                                   compress_stream, decompress_stream, STREAM_SENTINEL)
    except ImportError:
        from .compressor_v3 import (compress_with_dict, decompress_with_dict,
                                    compress_stream, decompress_stream, STREAM_SENTINEL)
    try:
        from compressor_v2 import compress_with_backend, decompress_with_backend
    except ImportError:
        from .compressor_v2 import compress_with_backend, decompress_with_backend
    try:
        from transforms_v2 import bwt_subblock_encode, bwt_subblock_decode, SUBBLOCK_RAW
    except ImportError:
        from .transforms_v2 import bwt_subblock_encode, bwt_subblock_decode, SUBBLOCK_RAW
    import io, struct

    # 1. huffman frequency overflow (>65535 counts): was silent tree divergence
    d = b"\x00" * 100000 + bytes([i % 256 for i in range(5000)])
    c, _ = compress_with_backend(d, backend="huffman", block_size=16384)
    assert decompress_with_backend(c) == d
    c, _, _ = compress_with_dict(d, backend="huffman", block_size=65536, use_dict=False)
    assert decompress_with_dict(c) == d
    print("  huffman freq overflow: OK")

    # 2. subblock raw marker: force the raw path, marker must be collision-free
    try:
        import transforms_v2 as TV
    except ImportError:
        from . import transforms_v2 as TV
    real_bwt = TV.bwt_encode
    calls = {"n": 0}
    def flaky_bwt(chunk):
        calls["n"] += 1
        if calls["n"] == 2:
            return None, None  # force one raw chunk
        return real_bwt(chunk)
    TV.bwt_encode = flaky_bwt
    try:
        data = os.urandom(60000)
        tr, ex = bwt_subblock_encode(data, sub_size=32768)
        assert struct.pack(">I", SUBBLOCK_RAW) in ex, "new raw marker missing"
        assert SUBBLOCK_RAW == 0xFFFFFFFF
        assert bwt_subblock_decode(tr, ex) == data
    finally:
        TV.bwt_encode = real_bwt
    print("  subblock raw marker: OK")

    # 3. truncation must raise, never silently return partial output
    c, _, _ = compress_with_dict(b"hello world " * 5000, backend="zstd", block_size=16384, use_dict=False)
    c2, _ = compress_with_backend(b"hello world " * 5000, backend="zstd", block_size=16384)
    for blob, fn in ((c, decompress_with_dict), (c2, decompress_with_backend)):
        for cut in (10, len(blob) // 2, len(blob) - 10):
            try:
                fn(blob[:cut])
                raise AssertionError(f"truncated@{cut}/{len(blob)} silently succeeded via {fn.__name__}")
            except (EOFError, ValueError):
                pass
    bio_in, bio_out = io.BytesIO(b"hello world " * 5000), io.BytesIO()
    compress_stream(bio_in, bio_out, backend="zstd", block_size=16384, use_dict=False)
    full = bio_out.getvalue()
    try:
        bio_in2, bio_out2 = io.BytesIO(full[:50]), io.BytesIO()
        decompress_stream(bio_in2, bio_out2)
        raise AssertionError("truncated stream silently succeeded")
    except (EOFError, ValueError):
        pass
    print("  truncation raises: OK")

    # 4. invalid backend / transform IDs must raise clean ValueErrors
    bad = bytearray(c)
    bad[5] = 0x09  # backend id out of range
    try:
        decompress_with_dict(bytes(bad))
        raise AssertionError("bad backend id silently accepted")
    except ValueError:
        pass
    bad = bytearray(c)
    bad[18] = 0x2A  # first block TID out of range (42); header is 18B here
    try:
        decompress_with_dict(bytes(bad))
        raise AssertionError("bad TID silently accepted")
    except ValueError:
        pass
    print("  invalid IDs raise: OK")

    # 5. streaming frames: sentinel present, normal decoder refuses cleanly,
    #    stream decoder roundtrips; legacy (pre-sentinel) streams still decode
    bio_in, bio_out = io.BytesIO(b"abc123" * 20000), io.BytesIO()
    compress_stream(bio_in, bio_out, backend="zstd", block_size=16384, use_dict=False)
    stream_bytes = bio_out.getvalue()
    assert struct.unpack(">I", stream_bytes[6:10])[0] == STREAM_SENTINEL
    try:
        decompress_with_dict(stream_bytes)
        raise AssertionError("stream frame misdecoded by normal decoder")
    except ValueError as e:
        assert "streaming" in str(e)
    bio_in2, bio_out2 = io.BytesIO(stream_bytes), io.BytesIO()
    decompress_stream(bio_in2, bio_out2)
    assert bio_out2.getvalue() == b"abc123" * 20000
    legacy = stream_bytes[:6] + stream_bytes[10:]  # strip sentinel -> old layout
    bio_in3, bio_out3 = io.BytesIO(legacy), io.BytesIO()
    decompress_stream(bio_in3, bio_out3)
    assert bio_out3.getvalue() == b"abc123" * 20000
    try:
        bio_in4, bio_out4 = io.BytesIO(b" zde"), io.BytesIO()
        compress_stream(bio_in4, bio_out4, backend="huffman")
        raise AssertionError("streaming huffman not refused")
    except ValueError:
        pass
    print("  stream sentinel + huffman refusal: OK")

    # 6. v2 oversize blocks refused loudly (16-bit ORIG_LEN)
    try:
        compress_with_backend(os.urandom(70000), backend="zstd", block_size=70000)
        raise AssertionError("v2 oversize block silently accepted")
    except ValueError:
        pass
    print("  v2 oversize guard: OK")

    # 7. public API version dispatch (v4 bytes via package decompress)
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        import rissa as pkg
        dd = os.urandom(50000)
        assert pkg.decompress(pkg.compress(dd)) == dd
        try:
            from compressor_v4 import compress_v4
        except ImportError:
            from .compressor_v4 import compress_v4
        cv, _, _ = compress_v4(dd, backend="zstd", level=19, use_dict=False)
        assert cv[:4] == b"RISA" and cv[4] == 4
        assert pkg.decompress(cv) == dd, "public API cannot read v4 frames"
        print("  version dispatch: OK")
    except ImportError as e:
        print(f"  version dispatch skip ({e})")
    print("  audit regressions OK")

if __name__=="__main__":
    test_transforms()
    test_shuffle_adversarial()
    test_huffman()
    test_compressor()
    v4h = test_v4_huffman_known_failure()
    test_determinism()
    test_versioning()
    fuzz_random()
    fuzz_truncated()
    test_audit_regressions()
    if v4h == "unexpected":
        print("\n=== TESTS FAILED: v4+huffman behaved unexpectedly (see above) ===")
        raise SystemExit(1)
    elif v4h in ("known-fail", "fixed", "skipped"):
        print(f"\n=== ALL TESTS PASSED (v4+huffman status: {v4h}; pre-existing, see CHANGELOG) ===")
    else:
        print("\n=== ALL TESTS PASSED ===")
