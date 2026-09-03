"""
Phase 3: Real Corpus Evaluation - NOAA (sensors), Loghub (logs), Yellow Taxi (Parquet)
Benchmark Bits/Symbol vs Shannon Entropy & zstd/xz baseline. Per-block MDL 64K.
"""
import os, math, struct, time, pathlib
from collections import Counter

def shannon(data: bytes):
    if not data: return 0.0
    c=Counter(data)
    n=len(data)
    return -sum((v/n)*math.log2(v/n) for v in c.values())

def bench_one(name, data: bytes):
    import lzma, zlib
    import zstandard as zstd
    from compressor_v3 import compress_with_dict
    ent=shannon(data)
    shannon_bytes=ent/8*len(data)
    print(f"\n{name} {len(data)}B entropy {ent:.2f} b/B shannon {shannon_bytes:.0f}B ({shannon_bytes/len(data)*100:.0f}%)")
    # baselines
    baselines={}
    baselines['zlib9']=len(zlib.compress(data,9))
    baselines['xz9']=len(lzma.compress(data, preset=9))
    baselines['zstd19']=len(zstd.ZstdCompressor(level=19).compress(data))
    baselines['zstd22']=len(zstd.ZstdCompressor(level=22).compress(data))
    for k,v in baselines.items():
        print(f"  {k:10} {v:8} {v/len(data)*100:4.0f}% {v*8/len(data):4.2f} b/sym { (v-shannon_bytes)/shannon_bytes*100:+5.1f}% over shannon")
    # ours 64K and 128K + dict
    for bs in [65536, 131072]:
        for use_dict in [False, True]:
            comp, hist, d = compress_with_dict(data, backend='zstd', level=19, block_size=bs, use_dict=use_dict)
            bsym=len(comp)*8/len(data) if data else 0
            print(f"  ours-zstd bs={bs//1024}K dict={use_dict} {len(comp):8} {len(comp)/len(data)*100:4.0f}% {bsym:4.2f} b/sym {hist.most_common(2)} dict {len(d) if d else 0}")

def gen_noaa(n=500000):
    """Synthetic NOAA-like: timestamp (delta) + 3x float sensor (temp/hum/pressure) - shows FLOAT_SPLIT+SHUFFLE win"""
    import random, struct
    out=bytearray()
    ts=1609459200
    for i in range(n//16):
        ts+=1 + random.randint(-2,2)  # delta with jitter -> DELTA_ZIGZAG wins
        temp=20+5*math.sin(i*0.01)+random.gauss(0,0.5)
        hum=60+10*math.sin(i*0.02)+random.gauss(0,1)
        pres=1013+3*math.sin(i*0.005)+random.gauss(0,0.2)
        out.extend(struct.pack('<I', ts))
        out.extend(struct.pack('<f', temp))
        out.extend(struct.pack('<f', hum))
        out.extend(struct.pack('<f', pres))
    return bytes(out)

def gen_loghub(n=500000):
    """Loghub-like: timestamp + level + message - text with structure -> ORDER2/SHUFFLE"""
    import random
    levels=[b"INFO ", b"WARN ", b"ERROR", b"DEBUG"]
    msgs=[b"connection from 192.168.1.", b"user login id=", b"sensor reading temp=", b"disk usage "]
    out=bytearray()
    for i in range(n//80):
        out.extend(f"2024-01-{(i%30)+1:02d} 12:00:{i%60:02d} ".encode())
        out.extend(random.choice(levels))
        out.extend(random.choice(msgs))
        out.extend(str(i%1000).encode()+b"\n")
    return bytes(out)[:n]

def gen_yellow_taxi(n=500000):
    """Yellow Taxi Parquet-like: columnar 4x int32 + 2x float64 - SHUFFLE+BIT_TRANSPOSE wins"""
    import random, struct
    out=bytearray()
    # simulate columnar: 6 columns, 1000 rows
    rows=n//32
    for i in range(rows):
        out.extend(struct.pack('<I', 100000+i))  # vendor
        out.extend(struct.pack('<I', random.randint(1,6)))  # passengers
        out.extend(struct.pack('<I', random.randint(100, 5000)))  # distance *100
        out.extend(struct.pack('<I', 1609459200+i*60))  # time delta
        out.extend(struct.pack('<d', random.gauss(15,5)))  # fare float64
        out.extend(struct.pack('<d', random.gauss(3,1)))  # tip
    return bytes(out)[:n]

if __name__=="__main__":
    # Try real download, fallback to synthetic if no internet
    base=pathlib.Path("deep_compress/corpora")
    base.mkdir(parents=True, exist_ok=True)
    # NOAA: try to fetch small NOAA sample, else synthetic
    print("Phase 3 corpora: NOAA (sensors), Loghub (logs), Yellow Taxi (Parquet)")
    print("If real files not in deep_compress/corpora/, using synthetic generators that match structure (see gen_*). Replace with real for final numbers.")
    # Check for real files
    real_files=list(base.glob("*"))
    if real_files:
        for p in real_files[:3]:
            data=p.read_bytes()[:2_000_000]  # sample 2MB for quick bench
            bench_one(f"REAL {p.name}", data)
    else:
        bench_one("NOAA-sensor (synthetic 500KB, ts+float)", gen_noaa())
        bench_one("Loghub-logs (synthetic 500KB, timestamp+level)", gen_loghub())
        bench_one("YellowTaxi-parquet (synthetic 500KB, columnar int/float)", gen_yellow_taxi())
        print("\nTo ingest real: place NOAA csv, Loghub logs, taxi parquet (or converted to csv) in deep_compress/corpora/ and rerun.")
