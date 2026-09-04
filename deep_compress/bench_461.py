"""4.6.1 benchmark: fast corpora, comp+decomp wall time, MB/s both directions,
ratio vs xz -9 / zstd-19, bits/sym + Shannon entropy. JSONL output for chunked runs.

Usage:
  python deep_compress/bench_461.py --only micro,silesia-dickens --out bench461.jsonl
  python deep_compress/bench_461.py --list
"""
import time, os, sys, json, math, argparse, pathlib
sys.path.insert(0, os.path.dirname(__file__))
from collections import Counter

def shannon(d: bytes) -> float:
    if not d:
        return 0.0
    c = Counter(d)
    n = len(d)
    return -sum((v / n) * math.log2(v / n) for v in c.values())

def get_datasets():
    import struct, random, math
    ds = {}
    # Silesia 1MB samples (fast, still real data)
    for name in ["dickens", "nci", "xml", "sao", "x-ray", "mozilla"]:
        p = pathlib.Path(__file__).parent / "silesia" / name
        if p.exists():
            ds[f"silesia-{name}-1M"] = p.read_bytes()[:1024 * 1024]
    # Synthetic structured
    random.seed(0)
    json_data = (b'{"timestamp":1609459200,"level":"INFO","msg":"connection from 192.168.1.1","user":123}\n' * 20000)[:1024 * 1024]
    ds["json-log-1M"] = json_data
    sensor = bytearray()
    ts = 1609459200
    for i in range(60000):
        ts += 1
        sensor.extend(struct.pack('<If', ts, 20 + 5 * math.sin(i * 0.01)))
    ds["sensor-1M"] = bytes(sensor[:1024 * 1024])
    col = bytearray()
    for i in range(90000):
        col.extend(struct.pack('<III', i % 1000, i % 5000, 1609459200 + i))
        if len(col) >= 1024 * 1024:
            break
    ds["columnar-1M"] = bytes(col[:1024 * 1024])
    ds["counter-1M"] = bytes([i % 256 for i in range(1024 * 1024)])
    return ds

def bench_micro():
    """C vs Python transform microbenchmarks, 1M buffer, MB/s."""
    import os as _os
    from transforms_v2 import (
        shuffle_encode, bit_transpose_encode, delta_encode,
        HAS_C_SHUFFLE, HAS_C_BIT, HAS_C_DELTA,
    )
    out = {"suite": "micro", "c_flags": {
        "shuffle": HAS_C_SHUFFLE, "bit": HAS_C_BIT, "delta": HAS_C_DELTA}}
    data = _os.urandom(1024 * 1024)
    reps = 5
    cases = [("shuffle", lambda d: shuffle_encode(d, 4)),
             ("bit", bit_transpose_encode),
             ("delta", delta_encode)]
    for name, fn in cases:
        t0 = time.perf_counter()
        for _ in range(reps):
            fn(data)
        dt = (time.perf_counter() - t0) / reps
        out[name] = {"sec_per_1M": round(dt, 4), "MB_s": round(1.0 / dt, 1)}
    # correctness spot check vs raw C entry points
    try:
        import rissa.c_shuffle, rissa.c_bit, rissa.c_delta
        assert rissa.c_shuffle.shuffle(data, 4) == shuffle_encode(data, 4)
        assert rissa.c_bit.bit_transpose(data) == bit_transpose_encode(data)
        assert rissa.c_delta.delta(data) == delta_encode(data)
        out["bit_identical"] = True
    except ImportError:
        out["bit_identical"] = "no-pyd"
    return out

def bench_data(name, data: bytes):
    import lzma
    import zstandard as zstd
    from compressor_v4 import compress_v4, decompress_v4
    r = {"suite": "data", "name": name, "orig": len(data),
         "entropy_bpb": round(shannon(data), 3)}
    # baselines with time
    t0 = time.perf_counter()
    xz = lzma.compress(data, preset=9)
    r["xz9"] = {"size": len(xz), "sec": round(time.perf_counter() - t0, 3)}
    t0 = time.perf_counter()
    z = zstd.ZstdCompressor(level=19).compress(data)
    r["zstd19"] = {"size": len(z), "sec": round(time.perf_counter() - t0, 3)}
    # rissa single 1M block
    t0 = time.perf_counter()
    comp, hist, _ = compress_v4(data, backend="lzma", block_size=len(data), use_dict=False)
    ct = time.perf_counter() - t0
    t0 = time.perf_counter()
    dec = decompress_v4(comp)
    dt = time.perf_counter() - t0
    assert dec == data, f"roundtrip FAIL {name}"
    r["rissa"] = {"size": len(comp), "comp_sec": round(ct, 3), "decomp_sec": round(dt, 3),
                  "comp_MBps": round(len(data) / ct / 1e6, 2),
                  "decomp_MBps": round(len(data) / dt / 1e6, 1),
                  "hist": dict(hist),
                  "bits_per_sym": round(len(comp) * 8 / len(data), 3),
                  "vs_xz_pct": round((len(comp) - len(xz)) / len(xz) * 100, 2)}
    return r

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="all", help="comma list or 'all'")
    ap.add_argument("--out", default="bench461.jsonl")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    ds = get_datasets()
    if a.list:
        print("micro," + ",".join(sorted(ds)))
        return
    only = set(a.only.split(",")) if a.only != "all" else None
    results = []
    if only is None or "micro" in only:
        print("== micro ==", flush=True)
        r = bench_micro()
        print(r, flush=True)
        results.append(r)
    for name in sorted(ds):
        if only is not None and name not in only:
            continue
        print(f"== {name} ({len(ds[name])}B) ==", flush=True)
        r = bench_data(name, ds[name])
        print(json.dumps(r), flush=True)
        results.append(r)
    with open(a.out, "a", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    print(f"appended {len(results)} rows -> {a.out}", flush=True)

if __name__ == "__main__":
    main()
