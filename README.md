# rissa

**Context-Selecting Compression Engine for Structured, Sensor, and Columnar Data**

`rissa` pays homage to **Jorma Rissanen** — Minimum Description Length (MDL) 1978. A fast, per-block adaptive compressor that beats generic LZ on time-series and columnar data.

**Live docs → https://rissa.web.app**

---

## Quick Install

```bash
pip install rissa-compress
rissa input.bin -o output.rissa
rissa -d output.rissa -o restored.bin
```

Or from source:

```bash
git clone https://github.com/your/rissa && cd rissa
pip install -e .
python -m deep_compress.rissa input.bin -o output.rissa
```

---

## Core Philosophy

$$
\text{Compressed} = \min_{T} \left[ \text{Cost}(T) + \text{Cost}(\text{Model}) + \text{Cost}(\text{Data} \mid \text{Model}) \right]
$$

A computable, context-selecting approximation of Minimum Description Length (MDL) [Rissanen 1978]. Instead of one static model, rissa searches 16 reversible transforms per block and keeps the exact MDL winner.

---

## Why rissa Exists

**The Gap:** Standard sliding-window tools (`zstd`, `xz`, `gzip`) use LZ77 match-finding and order-0 byte entropy. They excel on text but miss mathematical patterns in 32-bit/64-bit integers, IEEE 754 floats, and fixed-width sensor records.

**The Solution:** rissa evaluates a library of candidate transforms (`DELTA`, `SHUFFLE`, `FLOAT_SPLIT`, `BWT`, `BIT_TRANSPOSE` ...) on every 64K/128K block, selecting the transform that yields the lowest description length before entropy coding.

---

## Architecture — 4-Layer Stack

| Layer | Component | Function |
|-------|-----------|----------|
| **1** | **Transform Search** | 16 per-block reversible transforms (`DELTA2_ZIGZAG`, `SHUFFLE_4`, `FLOAT_SPLIT`, `BIT_TRANSPOSE`, `SHUFFLE4_DELTA`) — `deep_compress/transforms_v2.py` |
| **2** | **Global Dictionary** | Shared static/trained pass (1MB sample → 64KB header, MDL-gated) for cross-block redundancy — `deep_compress/compressor_v3.py` |
| **3** | **Entropy Coder** | Order-0 Huffman / rANS range coding (`deep_compress/huffman.py` → `rans.py`) |
| **4** | **Predictor Ensemble** | Optional high-ratio mixing predictors (`--ultra` mode) — `compressor_v3.py` |

- Streaming: `for block in stream` without whole-file RAM (`compress_stream`)
- Format: `MAGIC RISA v3` `BLOCK 64K/128K` `ext .rissa` — deterministic, versioned

Full theory → [`deep_compress/THEORY.md`](deep_compress/THEORY.md) · Architecture → [`deep_compress/ARCHITECTURE.md`](deep_compress/ARCHITECTURE.md)

---

## Benchmarks

Real data, not synthetic counters. `Silesia 12×212MB` + `NOAA` + `Loghub` + `NYC Yellow Taxi Parquet`.

| Corpus | xz -9 | zstd -19 | rissa 128K (zstd) | Bits/Sym vs Shannon |
|--------|-------|----------|-------------------|---------------------|
| NOAA binary sensor 500K (ts+float) | 213K 3.41 | 292K | **238K** `SHUFFLE_8` 3.82 | 6.83 ent, -12% vs xz |
| Yellow Taxi parquet 2MB (already compressed, ent 8.00) | 1,997K | 1,996K | **1,996K tie** `SHUFFLE_8` | 7.99 at Shannon limit |
| Silesia `dickens` 2MB (text) | **586K** | 592K | 714K `RAW` | per-block loses cross-block dict — needs shared dict on >1MB |
| Loghub `HDFS` 287K | **42K** | 42K | 44K `RAW` | small-file header overhead |

> Per-block alone cannot beat `xz` 8MB window on general text — rissa wins where transforms expose structure (sensor/columnar). See [`deep_compress/PHASE3_REPORT.md`](deep_compress/PHASE3_REPORT.md) and run `python deep_compress/final_bench.py`.

Reproduce:

```bash
python deep_compress/download_corpora.py   # Silesia + corpora
python deep_compress/test_roundtrip.py     # 16T + 200 fuzz — ALL PASSED
python deep_compress/final_bench.py
```

---

## Quick Code & CLI Example

**Python:**

```python
import rissa

# Compress structured float/sensor stream
data = open("telemetry.bin", "rb").read()
compressed = rissa.compress(data, level=3)

# Decompress back to original bytes
decompressed = rissa.decompress(compressed)
assert decompressed == data
```

Direct `deep_compress` API:

```python
from deep_compress.compressor_v3 import compress_with_dict, decompress_with_dict
comp, hist, d = compress_with_dict(data, backend="zstd", block_size=131072, use_dict=True)
assert decompress_with_dict(comp) == data
```

**CLI:**

```bash
rissa input.bin -o output.rissa --block 131072 --dict
rissa -d output.rissa -o restored.bin
rissa --stream in.bin -o out.rissa --block 131072
rissa --help
```

---

## Open Source & License

**License:** Apache 2.0 — Open-Source & Patent-Safe. See [`LICENSE`](LICENSE).

**Links:** [GitHub Repository](https://github.com/your/rissa) · [Issue Tracker](https://github.com/your/rissa/issues) · [PyPI rissa-compress](https://pypi.org/project/rissa-compress/)

**References:**
- Jorma Rissanen — Minimum Description Length (MDL), 1978
- A.N. Kolmogorov — Kolmogorov Complexity, 1965
- Duda — Asymmetric Numeral Systems (rANS)
- Mahoney — PAQ / Context Mixing

**Docs:** https://rissa.web.app
