"""v4.6.3 rigorous bench: repeated trials (median/stdev), peak RSS, CPU%,
and search/transform/backend time split. JSONL output. (Checklist item 7.)

Usage:
  python deep_compress/bench_463.py --reps 5 --only micro,fits-file --out bench463.jsonl
  python deep_compress/bench_463.py --list
"""
import argparse
import ctypes
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))


def peak_rss_mb():
    """Peak working set of this process in MB (Windows, no deps)."""
    try:
        class PMI(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

        pmi = PMI()
        pmi.cb = ctypes.sizeof(PMI)
        # NOTE: argtypes are mandatory here. Without them ctypes truncates the
        # pseudo-handle to 32 bits and GetProcessMemoryInfo fails with error 6.
        ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        ctypes.windll.psapi.GetProcessMemoryInfo.restype = ctypes.c_int
        h = ctypes.windll.kernel32.GetCurrentProcess()
        if ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(pmi), pmi.cb):
            return round(pmi.PeakWorkingSetSize / 1e6, 1)
    except Exception:
        pass
    try:
        import resource
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e3, 1)
    except Exception:
        return -1.0


def get_datasets():
    import pathlib
    import struct
    import math
    ds = {}
    for name in ["dickens", "nci", "xml", "x-ray"]:
        p = pathlib.Path(__file__).parent / "silesia" / name
        if p.exists():
            ds[f"silesia-{name}-1M"] = p.read_bytes()[:1024 * 1024]
    sensor = bytearray()
    ts = 1609459200
    for i in range(60000):
        ts += 1
        sensor.extend(struct.pack("<If", ts, 20 + 5 * math.sin(i * 0.01)))
    ds["sensor-480K"] = bytes(sensor)
    col = bytearray()
    for i in range(90000):
        col.extend(struct.pack("<III", i % 1000, i % 5000, 1609459200 + i))
        if len(col) >= 1024 * 1024:
            break
    ds["columnar-1M"] = bytes(col[:1024 * 1024])
    fits = pathlib.Path(__file__).parent.parent / "FOCx38i0101t_c0f.fits"
    if fits.exists():
        ds["fits-4M"] = fits.read_bytes()
    return ds


def bench_split(blk):
    """Time transform search vs backend encodes separately on one block."""
    import lzma
    from transforms_v2 import TRANSFORMS_V2
    t0 = time.perf_counter()
    outs = []
    for tid in sorted(TRANSFORMS_V2):
        name, enc, dec = TRANSFORMS_V2[tid]
        if tid in (5, 12) and len(blk) > 2048:
            continue
        tr, ex = enc(blk)
        if tr is not None:
            outs.append((tr, ex))
    t_trans = time.perf_counter() - t0
    t0 = time.perf_counter()
    for tr, ex in outs:
        lzma.compress(tr, preset=9)
    t_back = time.perf_counter() - t0
    return t_trans, t_back, len(outs)


def bench_end_to_end(name, data, reps, file_level=False):
    import lzma
    from compressor_v4 import compress_v4, decompress_v4
    from compressor_v3 import compress_with_dict, decompress_with_dict
    # Baselines re-timed on EVERY run: machine state drifts between sessions
    # (observed 3.5x), so ratios are only meaningful against same-run baselines.
    t0 = time.perf_counter()
    xz = lzma.compress(data, preset=9)
    xz_s = time.perf_counter() - t0
    comp_times, decomp_times, cpu_pcts, sizes = [], [], [], []
    hist = {}
    for _ in range(reps):
        if file_level:
            fn_c = lambda: compress_with_dict(data, backend="zstd", level=19,
                                              block_size=65536, use_dict=False, fast=True)
            fn_d = lambda c: decompress_with_dict(c)
        else:
            fn_c = lambda: compress_v4(data, backend="lzma", level=9,
                                       block_size=len(data), use_dict=False)
            fn_d = lambda c: decompress_v4(c)
        t0 = time.perf_counter()
        p0 = time.process_time()
        comp, h, _ = fn_c()
        cpu_pcts.append((time.process_time() - p0) / max(time.perf_counter() - t0, 1e-9))
        ct = time.perf_counter() - t0
        t0 = time.perf_counter()
        dec = fn_d(comp)
        dt = time.perf_counter() - t0
        assert dec == data, f"roundtrip FAIL {name}"
        comp_times.append(ct)
        decomp_times.append(dt)
        sizes.append(len(comp))
        hist = dict(h)
    assert len(set(sizes)) == 1, f"non-deterministic sizes {name}: {set(sizes)}"
    return {"suite": "e2e", "name": name, "orig": len(data), "reps": reps,
            "size": sizes[0], "hist": hist,
            "xz9_size": len(xz), "xz9_s": round(xz_s, 3),
            "comp_s_med": round(statistics.median(comp_times), 3),
            "comp_s_stdev": round(statistics.pstdev(comp_times), 3) if reps > 1 else 0.0,
            "decomp_s_med": round(statistics.median(decomp_times), 4),
            "cpu_pct_med": round(statistics.median(cpu_pcts) * 100, 1),
            "peak_rss_mb": peak_rss_mb()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--only", default="all")
    ap.add_argument("--out", default="bench463.jsonl")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    ds = get_datasets()
    if a.list:
        print("split," + ",".join(sorted(ds)))
        return
    only = set(a.only.split(",")) if a.only != "all" else None
    results = []
    if only is None or "split" in only:
        blk = ds["silesia-dickens-1M"][:65536] if "silesia-dickens-1M" in ds else next(iter(ds.values()))[:65536]
        tt, tb, n = bench_split(blk)
        r = {"suite": "split", "block": len(blk), "candidates": n,
             "transform_s": round(tt, 3), "backend_s": round(tb, 3),
             "transform_share": round(tt / max(tt + tb, 1e-9), 3)}
        print(r, flush=True)
        results.append(r)
    for name in sorted(ds):
        if only is not None and name not in only:
            continue
        print(f"== {name} x{a.reps} ==", flush=True)
        r = bench_end_to_end(name, ds[name], a.reps, file_level=(name == "fits-4M"))
        print(json.dumps(r), flush=True)
        results.append(r)
    with open(a.out, "a", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    print(f"appended {len(results)} rows -> {a.out}", flush=True)


if __name__ == "__main__":
    main()
