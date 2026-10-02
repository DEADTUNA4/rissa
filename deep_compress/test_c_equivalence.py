"""
Randomized C-vs-Python equivalence tests (v4.6.3 checklist item 5).

Every C-backed transform is compared against its pure-Python implementation
over randomized inputs, boundary sizes, and malformed data. Python reference
output is obtained by forcing the HAS_C_* flags off (they are read per call);
C output with flags on. Byte-identical or same-exception required. A crash
(access violation) fails the run implicitly — these tests must never crash.
"""
import os
import random
import sys
from collections import Counter
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(__file__))

import transforms_v2 as T
import huffman as H


@contextmanager
def py_mode():
    """Force all Python fallbacks (flags read per call, so toggling works)."""
    saved = (T.HAS_C_SHUFFLE, T.HAS_C_BIT, T.HAS_C_DELTA, T.HAS_C_TRANS, H.HAS_C_HUFF, H.HAS_C_STAT)
    T.HAS_C_SHUFFLE = T.HAS_C_BIT = T.HAS_C_DELTA = T.HAS_C_TRANS = False
    H.HAS_C_HUFF = H.HAS_C_STAT = False
    try:
        yield
    finally:
        (T.HAS_C_SHUFFLE, T.HAS_C_BIT, T.HAS_C_DELTA, T.HAS_C_TRANS,
         H.HAS_C_HUFF, H.HAS_C_STAT) = saved


def rand_data(rng, n, kinds=("random", "runs", "text", "zeros")):
    k = rng.choice(kinds)
    if k == "random":
        return bytes(rng.randrange(256) for _ in range(n))
    if k == "runs":
        out = bytearray()
        while len(out) < n:
            out.extend([rng.randrange(256)] * rng.randint(1, 300))
        return bytes(out[:n])
    if k == "text":
        words = [b"the ", b"quux ", b"a", b"compression ", b"\n", b"  ", b"0123456789"]
        out = bytearray()
        while len(out) < n:
            out.extend(rng.choice(words))
        return bytes(out[:n])
    out = bytearray(os.urandom(n))
    for _ in range(max(1, n // 50)):
        i = rng.randrange(max(1, n - 3))
        out[i:i + 2] = b"\x00\x00"
    return bytes(out)


def check_pair(name, fn, cases):
    """fn(data) must be identical in C and Python modes; exceptions must match in kind."""
    for i, d in enumerate(cases):
        try:
            with py_mode():
                a = fn(d)
            ae = None
        except Exception as e:  # noqa: BLE001 - comparing behavior
            a, ae = None, type(e).__name__
        try:
            b = fn(d)
            be = None
        except Exception as e:  # noqa: BLE001 - comparing behavior
            b, be = None, type(e).__name__
        assert ae == be, f"{name} case {i} len={len(d)}: py raised {ae}, C raised {be}"
        if ae is None:
            assert a == b, f"{name} case {i} len={len(d)}: {len(a)}B py vs {len(b)}B C"
    print(f"  {name}: OK ({len(cases)} cases)")


def sizes_for(max_n):
    base = [0, 1, 2, 3, 4, 5, 7, 8, 9, 15, 16, 17, 31, 33, 63, 65, 100, 255, 257,
            1000, 4095, 4097, 16384, 65535, 65536, 65537]
    return [n for n in base if n <= max_n]


def main():
    rng = random.Random(20261001)
    print("=== C-vs-Python equivalence ===")

    # 1. shuffle family (strides 2/4/8, encode + decode)
    for stride in (2, 4, 8):
        cases = [rand_data(rng, n) for n in sizes_for(70000) for _ in (0, 1)]
        check_pair(f"shuffle_{stride}", lambda d, s=stride: T.shuffle_encode(d, s), cases)
        check_pair(f"shuffle_dec_{stride}", lambda d, s=stride: T.shuffle_decode(d, s), cases)

    # 2. float split (+ non-%4 and tiny passthroughs)
    cases = [rand_data(rng, n) for n in sizes_for(70000) for _ in (0, 1)]
    check_pair("float_split", T.float_split_encode, cases)
    check_pair("float_split_dec", T.float_split_decode, cases)

    # 3. delta2 / xor / order2 / d2zz (+ decodes)
    pairs = [("delta2_encode", "delta2_decode"), ("xor_encode", "xor_decode"),
             ("order2_encode", "order2_decode"),
             ("delta2_zigzag_encode", "delta2_zigzag_decode")]
    for enc_n, dec_n in pairs:
        enc, dec = getattr(T, enc_n), getattr(T, dec_n)
    for enc_n, dec_n in pairs:
        enc, dec = getattr(T, enc_n), getattr(T, dec_n)
        cases = [rand_data(rng, n) for n in sizes_for(70000) for _ in (0, 1)]
        check_pair(enc_n, enc, cases)
        check_pair(dec_n, dec, cases)

    # 4. mtf (+ decode)
    cases = [rand_data(rng, n) for n in sizes_for(70000) for _ in (0, 1)]
    check_pair("mtf", T.mtf_encode, cases)
    check_pair("mtf_dec", T.mtf_decode, cases)

    # 5. RLE boundaries: runs at 258/259/260 zeros, 65534/65535/65536/70000 same-byte
    edge = [b"\x00" * n for n in (3, 4, 258, 259, 260, 518)]
    edge += [b"A" * n for n in (65534, 65535, 65536, 70000)]
    edge += [b"\xfe" * 70000, bytes([i % 3 for i in range(10000)])]
    cases = edge + [rand_data(rng, n) for n in (0, 1, 100, 5000, 70000)]
    check_pair("rle", T.rle_encode, cases)
    check_pair("rle_dec", T.rle_decode, cases)
    check_pair("rle_zero", T.rle_zero_encode, cases)
    check_pair("rle_zero_dec", T.rle_zero_decode, cases)

    # 6. BWT (Python reference is slow: cap sizes) + malformed primaries
    small = [rand_data(rng, n, kinds=("random", "runs", "text")) for n in
             (0, 1, 2, 3, 6, 11, 100, 1000, 4096) for _ in (0, 1)]
    small += [b"ab" * 1500, b"abc" * 1000, b"a" * 3000, b"banana" * 200]
    check_pair("bwt_encode", T.bwt_encode, small)
    bwts = []
    with py_mode():
        for d in small:
            b, p = T.bwt_encode(d)
            if b is not None:
                bwts.append((b, p))
    for i, (b, p) in enumerate(bwts):
        with py_mode():
            a = T.bwt_decode_fast(b, p)
        c = T.bwt_decode_fast(b, p)
        assert a == c, f"bwt_decode case {i}"
    print(f"  bwt_decode: OK ({len(bwts)} cases)")
    for bad_p in (-1, 4, 5, 65535, 2**31 - 1):  # n=4 below: all out of range
        for fn_mode in (False, True):
            try:
                if not fn_mode:
                    with py_mode():
                        T.bwt_decode_fast(b"\x01\x02\x03\x04", bad_p)
                else:
                    T.bwt_decode_fast(b"\x01\x02\x03\x04", bad_p)
                raised = None
            except Exception as e:  # noqa: BLE001
                raised = type(e).__name__
            assert raised == "ValueError", f"bad primary {bad_p} gave {raised}"
    print("  bwt_decode malformed: OK (ValueError both modes)")

    # 7. huffman pack/unpack + entropy
    hcases = [rand_data(rng, n) for n in (0, 1, 4, 100, 5000, 70000)]
    hcases.append(b"\x00" * 80000)  # overflow-adjacent single symbol
    def huff_rt(d):
        enc, freq, pad, _ = H.huffman_encode_block(d)
        return H.huffman_decode_block(enc, freq, pad, len(d))
    check_pair("huffman_roundtrip", huff_rt, hcases)
    for d in hcases:
        with py_mode():
            a = H.shannon_entropy(d)
        b = H.shannon_entropy(d)
        assert abs(a - b) < 1e-9, f"entropy {a} vs {b}"
    print("  shannon_entropy: OK")

    # 8. c_stat rank_ngrams vs Counter.most_common
    try:
        import rissa.c_stat as CS
    except ImportError:
        print("  rank_ngrams: SKIP (no c_stat)")
        CS = None
    if CS is not None:
        for window in (6, 8):
            for t in range(6):
                d = rand_data(rng, rng.choice([0, 10, 1000, 20000, 100000]))
                cnt = Counter()
                for k in range(len(d) - window + 1):
                    cnt[d[k:k + window]] += 1
                ref = [kv[0] for kv in cnt.most_common(4096) if kv[1] >= 3]
                got = CS.rank_ngrams(bytes(d), window, 3, 4096)
                assert got == ref, f"ngram w={window} trial {t}"
        print("  rank_ngrams: OK (randomized)")

    # 9. cdc_bounds vs the original Python loop (the spec it ports)
    try:
        import rissa.c_stat as CS2
    except ImportError:
        CS2 = None
    if CS2 is not None:
        def py_cdc(d, mask=0xFFF, poly=0xBF):
            chunks, h, start = [], 0, 0
            for i, b in enumerate(d):
                h = (h * poly + b) & 0xFFFFFFFF
                if (h & mask) == 0 or i - start >= 8192:
                    if i - start >= 1024:
                        chunks.append(d[start:i + 1])
                        start = i + 1
                if len(chunks) > 1024:
                    break
            if start < len(d):
                chunks.append(d[start:])
            return chunks
        for t in range(4):
            d = rand_data(rng, rng.choice([0, 500, 20000, 150000]))
            ref = py_cdc(d)
            got = [d[s:e] for s, e in CS2.cdc_bounds(bytes(d), 1024, 8192, 1024)]
            assert got == ref, f"cdc trial {t}"
        print("  cdc_bounds: OK (randomized)")

    print("=== ALL EQUIVALENCE TESTS PASSED ===")


if __name__ == "__main__":
    main()
