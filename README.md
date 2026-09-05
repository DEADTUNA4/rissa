# rissa

**Context-Selecting Compression Engine for Structured, Sensor, and Columnar Data**

`rissa` pays homage to **Jorma Rissanen** - Minimum Description Length (MDL) 1978.

**Live docs → https://rissa.web.app — v4.6.1 — Apache 2.0**

---

## What Rissa is

`rissa` is a per-block adaptive compressor. For each 64K-1M block it tries 19 reversible transforms (`DELTA`, `SHUFFLE`, `FLOAT_SPLIT`, `BWT`, `BIT_TRANSPOSE`) and keeps the one with lowest description length:

```
Compressed = min_T [ Cost(T) + Cost(Model) + Cost(Data | Model) ]
```

A computable approximation of MDL [Rissanen 1978]. `rissa` does not claim universal - it wins where structure exists.

- Format: `MAGIC RISA v4` `.rissa` `BLOCK 1M/4M adaptive` `19T` - deterministic, versioned
- Backends: `zstd`/`lzma`/`zlib`/`huffman` (range coder + rANS scaffolded only, not implemented — see `deep_compress/bwt_range.py:169-171`)
- Streaming: `for block in stream` without whole-file RAM

## Why it exists

**The Gap:** `zstd`, `xz`, `gzip` use LZ77 + order-0 entropy. Great on text, miss math in 32-bit/64-bit time-series ints, IEEE 754 floats, sensor records. The reverse is also true: rissa's per-block design can't see redundancy spanning blocks the way LZ's whole-file window can — hence the ties on general text below.

Example: `1,2,3,4` delta=1, 32-bit floats share exponent, sensor timestamps jitter -1. LZ sees nothing, `rissa` sees `DELTA_ZIGZAG` or `SHUFFLE_4`.

**The Solution:** Evaluate `DELTA`/`SHUFFLE`/`FLOAT_SPLIT`/`BWT` per block and pick the MDL winner before entropy coding. Falls back to `RAW` with ~32B total header (~0.003% at 1M) when no transform helps.

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

### Building the C extensions from source

The hot paths (`SHUFFLE`/`BIT`/`DELTA`, 111–308× vs Python) ship as
`rissa/c_*.c` with `setup.py` + `setup.cfg` already on main — no extra step:

```bash
python setup.py build_ext --inplace   # uses setup.cfg
python tools/rissa_tool.py doctor     # must show HAS_C_*=True
```

Run `doctor` after building: without it a broken toolchain fails
*silently* into correct-but-slow Python fallback (`HAS_C_*=False`).

Platform status, stated plainly: **Windows + MinGW-w64
(`E:\w64devkit`-style layout, `compiler=mingw32`) is the tested path.**
`setup.py` picks MSVC flags (`/O2 /arch:AVX2`) only with explicit
`--compiler=msvc`, and plain `-O3` (+AVX2 on x86-64) elsewhere — but
**Linux/Mac builds are untested, so treat non-Windows as
not-yet-cross-platform** until someone verifies a build there.

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

Honest numbers: Silesia 12-file corpus (211MB) + synthetic columnar. rissa ties `xz -9` on general data, wins where structure exists.

| Corpus | Size | xz -9 | rissa v4 single-block | Result |
|--------|------|-------|----------------------|--------|
| Silesia dickens | 9.9M | 2764K | 2764K `RAW` | tie +32B |
| Silesia mozilla | 50M | 13061K | 13061K `RAW` | tie +32B |
| Silesia mr | 9.7M | 2686K | 2686K `RAW` | tie +32B |
| Silesia nci | 32M | 1698K | 1698K `RAW` | tie +32B |
| Silesia ooffice | 6.0M | 2370K | 2370K `RAW` | tie +32B |
| Silesia osdb | 9.8M | 2783K | 2783K `RAW` | tie +32B |
| Silesia reymont | 6.4M | 1286K | 1286K `RAW` | tie +32B |
| Silesia samba | 21M | 3675K | 3675K `RAW` | tie +32B |
| Silesia sao | 7.0M | 4312K | 4312K `RAW` | tie +32B |
| Silesia webster | 40M | 8189K | 8189K `RAW` | tie +32B |
| Silesia **x-ray** | 8.2M | 4385K | **4212K** `BIT_PLANE` | **WIN -3.9%** |
| Silesia xml | 5.2M | 443K | 443K `RAW` | tie +32B |
| Columnar 3.6M *(synthetic)* | 3.6M | 204K | **39K** `SHUFFLE_8` | **WIN -80%** |
| Sensor 6M *(synthetic)* | 6M | 1610K | **1038K** `SHUFFLE` | **WIN -35%** |
| 5MB `x`×5M | 5M | 620 | 924 `RAW` | +32B header |

That's **11 ties + 1 real win + 2 synthetic wins**. Per-block MDL alone can't beat `xz`'s 8MB window on general text — rissa wins on bit-plane-separable and columnar data where transforms expose structure. Numbers below are v4 single-block runs (format frozen at v4); re-verified byte-identical at 4.6.1 on a 1M dickens spot-check (`310272`, `RAW`, roundtrip OK). Full tables `https://rissa.web.app/benchmarks.html` and `deep_compress/PHASE3_REPORT.md`.

Reproduce:

```bash
python deep_compress/download_corpora.py
python deep_compress/test_roundtrip.py  # 19T + 200 fuzz
python deep_compress/final_bench.py
```

---

**License:** Apache 2.0 — See [`LICENSE`](LICENSE) — **Docs:** https://rissa.web.app
