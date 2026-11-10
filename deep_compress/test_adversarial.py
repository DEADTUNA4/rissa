"""
Adversarial / robustness harness (added 4.6.6). The compressed byte stream
is attacker-controlled; these tests assert the FORMAT.md error contract on
malformed inputs and the 4.6.6 runtime guards (bounds.py). Plain script like
test_roundtrip.py: python deep_compress/test_adversarial.py
"""
import os
import random
import struct
import sys
import zlib

library_paths = (
    os.path.join(os.path.dirname(os.path.abspath(__file__))),
    os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")),
)
for p in library_paths:
    if p not in sys.path:
        sys.path.insert(0, p)

import transforms_v2 as T
import huffman as H
from bounds import OutputLimitError, DEFAULT_MAX_BLOCK_OUTPUT
import compressor_v2 as C2
import compressor_v3 as C3
import compressor_v4 as C4
import compressor_v3

_failures = []

def check(name, cond, detail=""):
    if cond:
        print(f"  {name}: OK")
    else:
        _failures.append(f"{name} {detail}")
        print(f"  {name}: FAIL {detail}")

def expect(name, fn, exc_type):
    try:
        fn()
        check(name, False, f" expected {exc_type.__name__}, no exception")
        return None
    except exc_type as e:
        check(name, True)
        return e
    except Exception as e:
        check(name, False, f" expected {exc_type.__name__}, got {type(e).__name__}: {e}")
        return None

#define helper to build v3 containers by hand. After rissa/? No: container writers
def v3_container(backend_id, blocks):
    """blocks = list of (tid, extra, orig_len, payload_bytes)
    payload already backend-compressed."""
    out = bytearray(b"RISA")
    out.append(3)
    out.append(backend_id)
    out.extend(struct.pack(">I", len(blocks)))
    out.extend(struct.pack(">I", 65536))
    out.extend(struct.pack(">I", 0))  # no dict
    for tid, extra, orig_len, payload in blocks:
        out.append(tid)
        out.append(len(extra))
        out.extend(struct.pack(">I", orig_len))
        out.extend(struct.pack(">I", len(payload)))
        out.extend(extra)
        out.extend(payload)
    return bytes(out)

def v3_data(backend, data):
    """A genuinely valid v3 container for reference/roundtrip checks."""
    comp, _, _ = C3.compress_with_dict(data, backend=backend, use_dict=False)
    return comp

def main():
    print("=== v3 container roundtrip (helper sanity) ===")
    data = os.urandom(10000)
    for backend in ["zlib", "lzma", "zstd"]:
        comp = v3_data(backend, data)
        check(f"v3 {backend} roundtrip", C3.decompress_with_dict(comp) == data)

    print("\n=== Bomb guard: backend output beyond expansion cap (v3) ===")
    # RAW + zlib, orig_len claims 100 but payload expands to > bound
    bomb_payload = zlib.compress(b"\x00" * 1_000_000)
    container = v3_container(1, [(0, b"", 100, bomb_payload)])
    expect("v3 RAW/zlib bomb rejected before allocation",
           lambda: C3.decompress_with_dict(container), OutputLimitError)
    # RLE (tid 19): ratio cap 3x
    rle_payload = zlib.compress(b"\x00" * 100_000)
    container = v3_container(1, [(19, b"", 1000, rle_payload)])
    expect("v3 RLE/zlib bomb rejected (3x cap)",
           lambda: C3.decompress_with_dict(container), OutputLimitError)
    # but a legitimately-shaped stream still decodes: orig_len = exact
    container = v3_container(1, [(0, b"", 1_000_000, bomb_payload)])
    dec = C3.decompress_with_dict(container)
    check("v3 valid bomb-shape block with honest ORIG_LEN decodes", dec == b"\x00" * 1_000_000)
    # and mismatched ORIG_LEN for a non-bombing payload still raises (old behavior)
    container = v3_container(1, [(0, b"", 1_000_000 + 5, bomb_payload)])
    expect("v3 length mismatch still FormatError",
           lambda: C3.decompress_with_dict(container), Exception) and None

    print("\n=== Bomb guard: per-block absolute cap ===")
    # huffman backend: ORIG_LEN drives the output allocation directly
    freq = [0] * 256
    freq[0] = 65535
    big = v3_container(0, [(0, b"", DEFAULT_MAX_BLOCK_OUTPUT + 1, b"\x00" * 8
                            )])
    # build proper huffman block layout to reach the decoder: header says
    # huffman backend -> pad + freq + enc_len fields
    out = bytearray(b"RISA")
    out.append(3)
    out.append(0)
    out.extend(struct.pack(">I", 1))
    out.extend(struct.pack(">I", 65536))
    out.extend(struct.pack(">I", 0))
    out.append(0)  # tid 0 RAW (allowed with huffman backend)
    out.append(0)  # extra_len
    out.extend(struct.pack(">I", DEFAULT_MAX_BLOCK_OUTPUT + 1))  # ORIG_LEN over cap
    out.append(0)  # padding
    for f in freq:
        out.extend(struct.pack(">H", f))
    out.extend(struct.pack(">I", 8))  # enc payload length
    out.extend(b"\x00" * 8)
    expect("v3 huffman ORIG_LEN over per-block cap rejected before decode",
           lambda: C3.decompress_with_dict(bytes(out)), Exception)

    print("\n=== Stream guard: strict length check replaces silent truncation ===")
    import io
    sample = b"rissa streaming strictness sample " * 400
    bio_in = io.BytesIO(sample)
    bio_out = io.BytesIO()
    C3.compress_stream(bio_in, bio_out, backend="zlib", use_dict=False)
    stream = bytearray(bio_out.getvalue())
    frame_len = 4 + 1 + 1 + 4 + 4 + 4  # header
    # header: magic4 + ver1(idx4) + backend1(idx5) + sentinel4 + blocksize4 + dictlen4
    hdr = 4 + 1 + 1 + 4 + 4 + 4
    if stream[4] == 3 and stream[5] == 1:
        # bump the ORIG_LEN of the first frame by 1 -> must raise now
        orig = struct.unpack(">I", stream[hdr + 2:hdr + 6])[0]
        stream[hdr + 2:hdr + 6] = struct.pack(">I", orig + 1)
        expect("stream corrupted frame raises (no silent truncation)",
               lambda: C3.decompress_stream(io.BytesIO(bytes(stream)), io.BytesIO()),
               Exception)
    else:
        check("stream strictness preconditions", False, "unexpected header layout")

    print("\n=== v4 header dict: bounded + DICT_LEN cross-check ===")
    dict_want = b"abcd" * 300  # 1200B
    dict_comp = zlib  # use raw lzma to force the "compressed with lzma" path
    import lzma as _lzma
    dc = _lzma.compress(dict_want, preset=9)
    def v4_with_dict(dict_comp, decl):
        out = bytearray(b"RISA")
        out.append(4)
        out.append(2)  # lzma backend
        out.extend(struct.pack(">I", 0))  # streaming 0 blocks (skip block loop)
        out.extend(struct.pack(">I", 65536))
        out.extend(struct.pack(">I", len(dict_comp)))
        out.extend(struct.pack(">I", decl))
        out.extend(dict_comp)
        return bytes(out)
    good = v4_with_dict(dc, len(dict_want))
    expect("v4 dict DICT_LEN mismatch raises",
           lambda: C4.decompress_v4(v4_with_dict(dc, len(dict_want) - 1)), Exception)
    # over-cap dict is rejected before decode
    expect("v4 dict over MAX_DICT_BYTES rejected",
           lambda: C4.decompress_v4(v4_with_dict(dc, 1 << 21)), Exception)

    print("\n=== max_output_size ceiling (whole stream) ===")
    data = os.urandom(200_000)
    comp = v3_data("zstd", data)
    check("no ceiling: decodes", C3.decompress_with_dict(comp) == data)
    expect("tiny ceiling raises OutputLimitError",
           lambda: C3.decompress_with_dict(comp, max_output_size=1000), OutputLimitError)
    check("exact ceiling: decodes", C3.decompress_with_dict(comp, max_output_size=len(data)) == data)
    comp4, _, _ = C4.compress_v4(data, block_size=65536, use_dict=False)
    check("v4 no ceiling", C4.decompress_v4(comp4) == data)
    expect("v4 tiny ceiling raises",
           lambda: C4.decompress_v4(comp4, max_output_size=1000), OutputLimitError)

    print("\n=== C-vs-Python error-path equivalence (fallback divergence) ===")
    # Adversarial containers whose transform-decode raises per-path.
    invalid_prim = struct.pack(">I", 10**9)  # BWT primary out of range
    mtf_data = b"\x00\x01\x02"*4
    container = v3_container(1, [(5, invalid_prim, 12, zlib.compress(mtf_data))])
    def decode_container():
        return C3.decompress_with_dict(container)
    # C path: rissa.c_trans.bwt_decode raises ValueError -> wrapped FormatError
    err_c = expect("BWT primary oob (C path)", decode_container, Exception)
    # Python path: force all C flags off
    saved = {k: getattr(T, k) for k in ("HAS_C_TRANS", "HAS_C_SHUFFLE", "HAS_C_BIT", "HAS_C_DELTA")}
    for k in saved:
        setattr(T, k, False)
    try:
        err_py = expect("BWT primary oob (Python path)", decode_container, Exception)
        check("same exception type C-vs-Python (BWT oob)",
              type(err_c) is type(err_py), f"{err_c!r} vs {err_py!r}")
    finally:
        for k, v in saved.items():
            setattr(T, k, v)

    # huffman padding out of range: C path must now raise instead of silently rerunning Python
    if H.HAS_C_HUFF:
        expect("huffman padding>7 raises via C path",
               lambda: H.huffman_decode_block(b"\x00", [1] + [0]*255, 99, 5), ValueError)
    else:
        check("huffman padding>7 (no C loaded, skipped)", False, "HAS_C_HUFF false - rebuild extensions first")

    print("\n=== v3/v2/v4 valid-stream byte-identity smoke (guards never fire) ===")
    data = b"hello world " * 3000 + bytes(range(256)) * 3 + b"\x00" * 5000
    for backend in ["huffman", "zlib", "lzma", "zstd"]:
        comp, _, _ = C3.compress_with_dict(data, backend=backend, use_dict=False)
        check(f"v3 {backend} guarded roundtrip", C3.decompress_with_dict(comp) == data)
        comp2, _ = C2.compress_with_backend(data, backend=backend)
        check(f"v2 {backend} guarded roundtrip", C2.decompress_with_backend(comp2) == data)
    comp4v, _, _ = C4.compress_v4(data, block_size=65536, use_dict=False)
    check("v4 guarded roundtrip", C4.decompress_v4(comp4v) == data)
    comp4d, _, _ = C4.compress_v4(data, block_size=65536, use_dict=True, force_dict=False)
    check("v4+dict guarded roundtrip", C4.decompress_v4(comp4d) == data)

    print("\n=== truncated containers still TruncatedError (regression) ===")
    comp = v3_data("zstd", data)
    for cut in (7, 20, len(comp) - 1):
        try:
            C3.decompress_with_dict(comp[:cut])
            check(f"truncated@{cut}", False, "should not have succeeded")
        except C3.TruncatedError:
            check(f"truncated@{cut}", True)
        except Exception as e:
            check(f"truncated@{cut}", False, f"{type(e).__name__}")

    print()
    if _failures:
        print(f"=== ADVERSARIAL FAILURES ({len(_failures)}) ===")
        for f in _failures:
            print(" -", f)
        sys.exit(1)
    print("=== ADVERSARIAL SUITE PASSED ===")

if __name__ == "__main__":
    main()
