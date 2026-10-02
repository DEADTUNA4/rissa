# Architecture and API Reference

**https://rissa.web.app/docs.html - organized by what you need, not by file listing.**

Three layers, in order. Do not mix them:

1. **Public API** (`rissa.compress` / `rissa.decompress`) - stable signatures, the only surface most code should touch.
2. **Containers** - v3 is what the public API writes today (stable default); v4 is the large-file/LZMA container, available via `deep_compress.compressor_v4` (opt-in). Both always decode.
3. **Internals** (`deep_compress.*`, `rissa/c_*.c`) - escape hatches. Signatures may change; behavior (bytes, roundtrips) must not.

For user guide see `GUIDE.md`, for byte-level format see `FORMAT.md`, for theory see `THEORY.md`.

## 1. Public API

```python
import rissa

compressed = rissa.compress(data)          # level=3, 64K blocks, zstd
original = rissa.decompress(compressed)    # any version: v2/v3/v4 dispatch
assert original == data
```

Full signature (already supports everything the review sketch asked for):

```python
rissa.compress(
    data: bytes,
    level: int = 3,            # 1->3, 2->6, 3->19, 4->22 (backend levels)
    block_size: int = 65536,
    backend: Backend = "zstd",  # "zstd" | "lzma" | "zlib" | "huffman"
    use_dict: bool = False,
    fast: bool = False,        # zstd-1 screen, top-4 + RAW; identical winners
) -> bytes
rissa.decompress(data: bytes) -> bytes  # raises FormatError/TruncatedError (both also ValueError/EOFError)
```

Errors live in `deep_compress.errors`: `RissaError` base, `TruncatedError(RissaError, EOFError)`, `FormatError(RissaError, ValueError)`. Backend library errors (`lzma.LZMAError`, `zstandard.ZstdError`) propagate unwrapped. `__all__ = ["compress", "decompress"]`.

Do not use `from deep_compress.compressor_v3 import ...` in application code unless you need histograms, dict bytes, or knobs the public API hides. That machinery is documented in section 7.

## 2. Compression pipeline

```
Input bytes
  ↓  split into blocks (64K/128K v3; 1M/4M adaptive, single block ≤4M, v4)
Transform search (19 reversible candidates per block, C-accelerated)
  ↓  per-block MDL: total = len(backend(transform)) + 1 + len(extra), keep min
MDL selection (BlockResult: transform_id, extra, payload, transform_name)
  ↓
Entropy backend (zstd default; lzma/zlib/huffman)
  ↓
.rissa container (MAGIC RISA, versioned, deterministic: same input → same bytes)
```

`fast=True` screens with same-family zstd-1 and fully encodes top-4 + RAW (measured: true-best missed 2/56 blocks, xml only). Exhaustive (`fast=False`) is the benchmark path. Blocks are independent: v3/v4 evaluate them on a ThreadPool (6 workers when >4 blocks) with ordered reassembly - parallel output is byte-identical by construction. `RISSA_STRICT=1` re-raises any suppressed candidate error (CI/debugging); default logs at debug and skips the candidate.

## 3. Transform reference

19 entries in `TRANSFORMS_V2` (`deep_compress/transforms_v2.py`), all `encode(data) -> (bytes, extra)` / `decode(bytes, extra) -> bytes`, reversible. Hot paths are C (`rissa/c_shuffle`, `c_bit`, `c_delta`, `c_trans`, `c_huff`, `c_stat`) behind `HAS_C_*` flags with Python fallback; `doctor` must show all True.

| TID | Name | Extra | When it wins |
|-----|------|-------|--------------|
| 0 | `RAW` | `b""` | fallback |
| 1 | `DELTA` | `b""` | counters, ramps |
| 2 | `XOR_DELTA` | `b""` | near-duplicate bytes |
| 3 | `DELTA2` | `b""` | linear ramps, sensor |
| 4 | `MTF` | `b""` | after BWT |
| 5 | `BWT_MTF` | `>I` primary | text ≤256K |
| 6/7/8 | `SHUFFLE_2/4/8` | `b"\x02/04/08"` | 16/32/64-bit columns |
| 9 | `DELTA_ZIGZAG` | `b""` | Gorilla-style jitter |
| 10 | `DELTA2_ZIGZAG` | `b""` | timestamps |
| 11 | `ORDER2` | `b""` | `2*prev - prev2` |
| 12 | `BWT_MTF_RLE` | `>I` primary | BWT+MTF+RLE 4-zero marker |
| 13 | `FLOAT_SPLIT` | `b"\x04"` | IEEE754 4-stream |
| 14 | `BIT_TRANSPOSE` | `b""` | 8x8 bit matrix |
| 15 | `SHUFFLE4_DELTA` | `b"\x04"` | composition (single-T accounting, see cost note) |
| 16 | `BWT_SUBBLOCK` | `>I sub_size + >I num + num×>I primaries` (`0xFFFFFFFF` = raw) | 1M→4×256K |
| 17 | `DICT_RESERVED` | `b""` | frozen identity stub (TID kept so old files decode) |
| 19 | `RLE` | `b""` | `>BH` pairs, runs split at 65535 |

(TID 18 `RACD` lives in `TRANSFORMS_EXPERIMENTAL`: ruled out on real text, gated.)

```python
from deep_compress.transforms_v2 import delta_encode, shuffle_encode
delta_encode(b"\x10\x11\x13")  # b"\x10\x01\x02"
shuffle_encode(b"abcd"*4, 4)   # b"aaaa bbbb cccc dddd"
```

## 4. Container format

`MAGIC RISA`, `VERSION` 1 byte (`VERSION = 4` in code; "v4.4" in old prose means the same frozen format v4, not a new version). v3 header: `MAGIC VER BACKEND NBLOCKS BSIZE DICTLEN DICT?`; v4 header adds `DICT_ORIG_LEN` + lzma-compressed dict. Blocks: `TID(1) EXTRA_LEN(1) ORIG_LEN(4) COMP_LEN(4) EXTRA? COMP`, all big-endian. Streaming frames carry `0xFFFFFFFF` in the block-count slot and decode only via `decompress_stream`. Full spec: `FORMAT.md`.

## 5. Backends

`zstd` (default, levels via public `level` 1-4 → 3/6/19/22), `lzma` (preset 9, `9|PRESET_EXTREME` on the v4 path to match `xz -9`), `zlib`, `huffman` (order-0, 512B table; counts above 65535 monotonically scaled before tree build so encoder/decoder share the stored table). `huffman` is refused for streaming (frames carry no frequency table). Types: `Backend = Literal["zstd", "lzma", "zlib", "huffman"]` (`deep_compress/api_types.py`).

## 6. Python API details

- `compress_with_dict(data, backend="zstd", level=19, block_size=65536, use_dict=True, fast=False, max_workers=None) -> tuple[bytes, Counter[str], bytes | None]` - returns `(bytes, histogram, dict_bytes)`. `max_workers`: None = auto (6 threads when >4 blocks), 1 = serial.
- `compress_v4(data, backend="lzma", level=9, block_size=1M, use_dict=True, ...)` - the v4-container path; shared `_eval_block_v4` for serial + parallel.
- `compress_stream(in, out, ...)` / `decompress_stream(in, out)` - constant-memory streaming (`block_size` is the memory knob).
- Shared dicts: v3 samples 1MB → 64KB (`zstandard.train_dictionary`, 6-gram fallback), MDL-gated (kept only if it pays); v4 builds an lzma `preset_dict` from top 8-grams + CDC chunks.
- Exceptions: `TruncatedError` (file ends mid-field, never partial output), `FormatError` (magic/version/ids/counts, cross-format feeds) - see `deep_compress/errors.py`.
- Types: `deep_compress/api_types.py` (`Backend`, `BlockResult` dataclass with `transform_id/extra/payload/transform_name`). Python floor is 3.9: modern hints via `from __future__ import annotations`, plain `@dataclass` (no 3.10 `slots=True`).

Example (escape hatch with inspection):

```python
from deep_compress.compressor_v3 import compress_with_dict, decompress_with_dict
comp, hist, d = compress_with_dict(data, backend="zstd", block_size=131072, use_dict=True)
print(hist)  # Counter({'SHUFFLE_8': 4})
assert decompress_with_dict(comp) == data
```

## 7. Developer internals

- `compressor_v3.py` - default path: 64K/128K, shared dict, streaming, fast screen, ThreadPool. Pure per-block `_eval_block_v3`.
- `compressor_v4.py` - 1M/4M adaptive, lzma dict, `_eval_block_v4` + `_write_block_v4` shared by serial/parallel. Special TIDs 99 (`XOR_PREV`, sequential only) and 100 (`BIT_PLANE`). v4+huffman backend decompress is a known pre-existing failure (CHANGELOG).
- `huffman.py` - order-0 + `shannon_entropy`; order-1 gated experimental. `bwt_range.py` - range-coder scaffold (experimental). `cdc_dict.py` - CDC substitution (experimental). `diag.py` - skip-note policy + `RISSA_STRICT`.
- C extensions (`rissa/c_*.c`, w64devkit GCC, `setup.py`; portable `-O3` default, `RISSA_NATIVE=1` for `-mavx2 -march=native`): shuffle/bit/delta + batch ports (generic shuffle, float-split, delta2, xor, order2, d2zz, mtf, rle, bwt radix, huffman pack, stats/ngrams/CDC). Equivalence suite: `deep_compress/test_c_equivalence.py`. Correctness gate: `deep_compress/test_roundtrip.py` (banner distinguishes PASS / KNOWN-FAILURE / UNEXPECTED for CI).
- Benchmarks: `deep_compress/bench_463.py --reps` (median/stdev, peak RSS, CPU%, per-run baselines, JSONL). Machine: ASUS TUF i7-8750H, `BENCHMARK_SYSTEM.md`. Key facts: transforms are ~2% of wall (backends 97%+); machine drift observed at 3.5× between sessions, so ratios only count against same-run baselines.
- Style: `import os` / `import sys` on separate lines; expanded try/except with named `exc`; targeted catches + `note()` (no bare `except:`); run `test_roundtrip.py` + `test_c_equivalence.py` before/after engine changes.
