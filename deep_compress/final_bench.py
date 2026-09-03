"""
Final comprehensive bench: Silesia + NOAA/Loghub/Yellow (raw) + synthetic, 64K/128K, dict MDL gated, multi-run time/memory, bits/sym vs Shannon
Tries to finish Phase 2-3 in one go.
"""
import os, pathlib, time, math, statistics, lzma, zlib, bz2, sys, struct
from collections import Counter
sys.path.insert(0, 'deep_compress' if os.path.exists('deep_compress') else '.')
try: import deep_compress  # when run from root
except: pass
from compressor_v3 import compress_with_dict, decompress_with_dict
try:
    from transforms_v2 import TRANSFORMS_V2
except ImportError:
    from .transforms_v2 import TRANSFORMS_V2
import zstandard as zstd
try: import psutil
except: psutil=None
try: import pyarrow.parquet as pq
except: pq=None

def shannon(d):
    if not d: return 0
    c=Counter(d)
    n=len(d)
    return -sum((v/n)*math.log2(v/n) for v in c.values())

def bench_once(data: bytes, block_size=131072):
    # ours 128K dict MDL gated inside compress_with_dict (dict auto-gated, so use_dict=True is safe)
    t0=time.perf_counter()
    comp, hist, d = compress_with_dict(data, backend='zstd', level=19, block_size=block_size, use_dict=True)
    t=time.perf_counter()-t0
    return len(comp), t, hist, d

def bench_baseline(data):
    res={}
    for name, fn in [
        ("zlib9", lambda d: len(zlib.compress(d,9))),
        ("xz9", lambda d: len(lzma.compress(d, preset=9))),
        ("bzip2", lambda d: len(bz2.compress(d,9))),
        ("zstd19", lambda d: len(zstd.ZstdCompressor(level=19).compress(d))),
        ("zstd22", lambda d: len(zstd.ZstdCompressor(level=22).compress(d))),
    ]:
        t0=time.perf_counter()
        sz=fn(data)
        t=time.perf_counter()-t0
        res[name]=(sz,t)
    return res

# 1. Yellow parquet -> raw CSV for columnar test
yellow_parq=pathlib.Path("deep_compress/corpora/yellow_tripdata_2023-01.parquet")
yellow_raw=None
if yellow_parq.exists() and pq:
    try:
        print(f"Converting parquet {yellow_parq.stat().st_size} -> raw columnar")
        # Try pyarrow, fallback to binary sample if truncated
        if yellow_parq.stat().st_size < 47000000:  # truncated download ~46.9MB vs 47.6 expected, try anyway
            print("  parquet appears truncated, using binary sample instead")
            yellow_raw=None
        else:
            table=pq.read_table(str(yellow_parq))
            import io
            df=table.slice(0, 200000).to_pandas()
            csv_buf=io.StringIO()
            df.to_csv(csv_buf, index=False)
            yellow_raw=csv_buf.getvalue().encode()
            print(f"  raw CSV {len(yellow_raw)} from 200k rows")
    except Exception as e:
        print(f"parquet convert fail {e} - using binary sample")
        yellow_raw=None

# 2. Collect corpora
corpora=[]
# Silesia subset (2 files for quick final, full would be 12*212MB heavy)
for name in ["dickens","sao"]:
    p=pathlib.Path(f"deep_compress/silesia/{name}")
    if p.exists():
        corpora.append((f"Silesia-{name}", p.read_bytes()[:2_000_000]))  # 2MB sample for quick multi-run
# NOAA, logs
for name, p in [("NOAA-csv","deep_compress/corpora/noaa_01001099999.csv"),
                ("Apache-log","deep_compress/corpora/Apache_2k.log"),
                ("HDFS-log","deep_compress/corpora/HDFS_2k.log")]:
    pp=pathlib.Path(p)
    if pp.exists():
        corpora.append((name, pp.read_bytes()))
# Yellow raw if available else parquet binary sample
if yellow_raw:
    corpora.append(("Yellow-CSV-200k", yellow_raw))
else:
    # fallback parquet binary sample
    if yellow_parq.exists():
        corpora.append(("Yellow-parquet-binary-2MB", yellow_parq.read_bytes()[:2_000_000]))
# synthetic binary sensor for win demonstration
def gen_noaa_bin(n=500000):
    import random
    out=bytearray()
    ts=1609459200
    for i in range(n//16):
        ts+=1+random.randint(-2,2)
        import math
        out.extend(struct.pack('<I', ts))
        out.extend(struct.pack('<f', 20+5*math.sin(i*0.01)))
        out.extend(struct.pack('<f', 60+10*math.sin(i*0.02)))
        out.extend(struct.pack('<f', 1013+3*math.sin(i*0.005)))
    return bytes(out)
corpora.append(("NOAA-binary-synth-500K", gen_noaa_bin()))

print(f"\nFinal bench: {len(corpora)} corpora, 3 runs each, 128K MDL gated")
print(f"{'name':24} {'orig':>8} {'ent':>5} {'zstd19':>8} {'xz9':>8} {'ours128K':>9} {'bits':>5} {'win':>6} hist")
print("-"*110)
for name, data in corpora:
    ent=shannon(data)
    # multi-run 3x for time variance
    times=[]
    sizes=[]
    for _ in range(3):
        sz,t,_,_=bench_once(data, block_size=131072)
        times.append(t); sizes.append(sz)
    sz_mean=statistics.mean(sizes)
    t_mean=statistics.mean(times)
    t_std=statistics.stdev(times) if len(times)>1 else 0
    base=bench_baseline(data)
    xz=base['xz9'][0]
    z19=base['zstd19'][0]
    bits=sz_mean*8/len(data) if data else 0
    win=xz-sz_mean
    winp=win/xz*100 if xz else 0
    # single hist
    _,_,hist,_=bench_once(data, block_size=131072)
    print(f"{name:24} {len(data):8} {ent:5.2f} {z19:8} {xz:8} {int(sz_mean):9} {bits:5.2f} {winp:+5.1f}% {t_mean:.2f}±{t_std:.2f}s {dict(hist.most_common(2))}")

# Also test composited SHUFFLE->DELTA vs single
print("\nComposition check: SHUFFLE_4 vs SHUFFLE4_DELTA on Yellow CSV")
if yellow_raw:
    import zlib
    from transforms_v2 import shuffle_encode, delta_encode
    sample=yellow_raw[:65536]
    for name, fn in [("RAW", lambda x: x),
                     ("SHUFFLE_4", lambda x: shuffle_encode(x,4)),
                     ("SHUFFLE4_DELTA", lambda x: __import__('transforms_v2').shuffle_delta_encode(x,4)),
                     ("BIT_TRANSPOSE", lambda x: __import__('transforms_v2').bit_transpose_encode(x))]:
        tr=fn(sample)
        print(f"  {name:15} {len(zlib.compress(tr,1)):6} est")
