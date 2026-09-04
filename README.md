# rissa

**Context-Selecting Compression Engine for Structured, Sensor, and Columnar Data**

`rissa` pays homage to **Jorma Rissanen** - Minimum Description Length (MDL) 1978.

**Live docs → https://rissa.web.app — v4.4 — Apache 2.0**

---

## What Rissa is

`rissa` is a per-block adaptive compressor. For each 64K-1M block it tries 19 reversible transforms (`DELTA`, `SHUFFLE`, `FLOAT_SPLIT`, `BWT`, `BIT_TRANSPOSE`) and keeps the one with lowest description length:

```
Compressed = min_T [ Cost(T) + Cost(Model) + Cost(Data | Model) ]
```

A computable approximation of MDL [Rissanen 1978]. `rissa` does not claim universal - it wins where structure exists.

- Format: `MAGIC RISA v4` `.rissa` `BLOCK 1M/4M adaptive` `16T` - deterministic, versioned
- Backends: `zstd`/`lzma`/`zlib`/`huffman` → `rANS` (gated `--experimental`)
- Streaming: `for block in stream` without whole-file RAM

## Why it exists

**The Gap:** `zstd`, `xz`, `gzip` use LZ77 + order-0 entropy. Great on text, miss math in 32-bit/64-bit time-series ints, IEEE 754 floats, sensor records.

Example: `1,2,3,4` delta=1, 32-bit floats share exponent, sensor timestamps jitter -1. LZ sees nothing, `rissa` sees `DELTA_ZIGZAG` or `SHUFFLE_4`.

**The Solution:** Evaluate `DELTA`/`SHUFFLE`/`FLOAT_SPLIT`/`BWT` per block and pick the MDL winner before entropy coding. Falls back to `RAW` with 0.4% header at 128K when no transform helps.

## Installation

```bash
pip install rissa-compress
```

Or from source:

```bash
git clone https://github.com/DEADTUNA4/rissa && cd rissa
pip install -e .
```

Requires `zstandard` (optional, falls back to `zlib`), Python 3.9+.

## Basic usage

```python
import rissa
data = open("telemetry.bin", "rb").read()
compressed = rissa.compress(data, level=3)  # 1:3 2:6 3:19 4:22
assert rissa.decompress(compressed) == data
```

```bash
rissa input.bin -o output.rissa --block 131072
rissa -d output.rissa -o restored.bin
rissa input.bin -o output.rissa --block 1048576 --dict  # shared dict
```

More → [`GUIDE.md`](GUIDE.md) · [`FORMAT.md`](FORMAT.md) · [`ARCHITECTURE.md`](ARCHITECTURE.md) · [`DEVELOPER.md`](DEVELOPER.md)

## Benchmarks

Real data, Silesia pending 68MB re-download for thesis test (was deleted for clean):

| Corpus | xz -9 | rissa 128K | Bits/Sym |
|--------|-------|------------|----------|
| NOAA binary sensor 500K | 213K | **238K** `SHUFFLE_8` | 3.82 vs 6.83 ent |
| Yellow Taxi parquet 2M (ent 8.00) | 1,997K | **1,996K tie** | 7.99 at limit |
| Silesia dickens 2MB | **586K** | 714K `RAW` | +21% need dict |
| Synthetic Counter 5KB | 324 | **71** `-78%` `DELTA` | proves transform |

Per-block alone loses cross-block on text - rissa wins on sensor/columnar where transforms expose structure. Full tables `https://rissa.web.app/benchmarks.html` and `deep_compress/PHASE3_REPORT.md`.

Reproduce:

```bash
python deep_compress/download_corpora.py
python deep_compress/test_roundtrip.py  # 16T + 200 fuzz
python deep_compress/final_bench.py
```

---

**License:** Apache 2.0 — See [`LICENSE`](LICENSE) — **Docs:** https://rissa.web.app
