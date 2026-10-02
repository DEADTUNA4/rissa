# Rissa Documentation

**https://rissa.web.app - Apache 2.0 - `pip install rissa-compress` - v4.6.4**

Three layers: **public API** (stable, writes the v3 container) - **containers** (v3 default, v4 for large-file/LZMA, both always decode) - **internals** (`deep_compress.*` escape hatches). Architecture overview: `DEVELOPER.md`. Byte-level spec: `FORMAT.md`.

---

## 1. Overview

### What Rissa does

Rissa is a per-block adaptive compressor for structured, sensor, and columnar data (32-bit/64-bit integers, IEEE 754 floats, telemetry records, medical images). For each block it tries 19 reversible transforms and keeps the one with the smallest total description length. Where no transform helps it falls back to `RAW` with ~32B of total header. Honest operating range: wins on bit-plane-separable and columnar data (Silesia x-ray -3.9%, NASA FITS -5.3%, synthetic columnar -80% / sensor -35%), ties `xz -9` within +32B on general data (11/12 Silesia files).

### MDL equation

```
Compressed = min_T [ Cost(T) + Cost(Model) + Cost(Data | Model) ]
```

Per block, concretely: `total = len(backend(transform(block))) + 1 + len(extra)` - backend payload plus 1 TID byte plus side info. Lowest total wins. (Jorma Rissanen, MDL 1978; homage in the name.)

### Current v4 architecture

- Format v4 containers (`MAGIC RISA`, `VERSION = 4`, frozen): 1M/4M adaptive blocks (single block for files ≤4M), lzma `preset_dict` trained per file, special TIDs 99 (`XOR_PREV`, sequential only) and 100 (`BIT_PLANE`).
- Engine paths: `compressor_v3` (default: 64K/128K, shared dict, streaming, fast screen, ThreadPool) and `compressor_v4` (1M/4M, shared `_eval_block_v4` for serial + parallel).
- Transforms in C (`rissa/c_*.c`, w64devkit GCC; portable `-O3` default, `RISSA_NATIVE=1` for `-mavx2 -march=native`).
- Deterministic: sorted TID iteration, no hash tie-breaks - same input gives same bytes. Thread parallelism reassembles in order (byte-identical to serial, proven).

---

## 2. Public Python API

```python
import rissa

compressed = rissa.compress(data)
original = rissa.decompress(compressed)
assert original == data
```

### `rissa.compress()`

```python
rissa.compress(
    data: bytes,
    level: int = 3,            # 1->3, 2->6, 3->19, 4->22 (backend levels); other ints pass through
    block_size: int = 65536,   # 4096, 16384, 65536, 131072
    backend: Backend = "zstd", # "zstd" | "lzma" | "zlib" | "huffman"
    use_dict: bool = False,    # 1MB sample -> 64KB shared dict, MDL-gated
    fast: bool = False,        # zstd-1 screen, top-4 + RAW; identical winners, ~3x faster
) -> bytes
```

- `data`: input bytes, any length (empty `b""` compresses to a valid one-block container).
- `level`: 1-4 map to backend-native levels (zstd 3/6/19/22; lzma/zlib clamp to their valid presets - pass 1-4, not raw preset numbers).
- `block_size`: split granularity. Larger blocks give backends bigger windows; smaller blocks isolate structure. 65536 default.
- `use_dict`: shared dictionary written once into the header and used for all blocks. Automatically disabled when it does not pay for itself (MDL gate).
- `backend`: entropy coder after the transform. `zstd` default (best all-round); `lzma` best ratio on text/image; `zlib` fastest portable; `huffman` pure-Python order-0 (no dependency).
- `fast`: two-stage MDL. Screen every transform with cheap zstd-1, fully encode top-4 + RAW with the real backend. Measured byte-identical to exhaustive on dickens/xml/x-ray/FITS at 2.6-4x speedup (56-block panel: true best missed 2/56, xml only).
- Returns a `.rissa` container (v3 layout); raises `ValueError` for unknown backend names.

### `rissa.decompress()`

```python
rissa.decompress(data: bytes) -> bytes  # any version: v2/v3/v4 dispatch on the VER byte
```

- `data`: bytes starting with `RISA` (any version) or legacy `DCM2`/`DCM3`/`DCMP`.
- Returns the original bytes; raises `TruncatedError` (file ends mid-field, never partial output) or `FormatError` (bad magic/version/ids, cross-format feeds). Both subclass the matching builtins (`EOFError`, `ValueError`) and derive from `RissaError` (`deep_compress/errors.py`).
- `__all__ = ["compress", "decompress"]`.

---

## 3. Compression Pipeline

```
Input bytes
  ↓  block splitting (data[i:i+block_size]; single [b""] for empty input)
Transform evaluation (every TID in TRANSFORMS_V2: enc(block) -> (transformed, extra))
  ↓  MDL cost per candidate: len(backend(transformed)) + 1 + len(extra)
Backend compression (zstd-19 / lzma-9 / zlib-9 / huffman per candidate)
  ↓  winner selection (strict min; ties keep the lower TID - deterministic)
Container writing (header once, then TID/EXTRA_LEN/ORIG_LEN/COMP_LEN/EXTRA/COMP per block)
```

- **Input**: `bytes` (slices are copied per block; streaming API avoids holding the whole file).
- **Block splitting**: list comprehension over `range(0, len(data), block_size)`. v4 adapts: `max_block` (≤15M) or ≤4M files become a single block to save header (5x1M 600B → single 32B).
- **Transform evaluation**: `enc(block)` returns `(transformed: bytes, extra: bytes)` or `(None, None)` when inapplicable (BWT over its cap). Exceptions in candidates are recorded (`deep_compress/diag.py`) and skipped; `RISSA_STRICT=1` re-raises immediately.
- **MDL cost**: `total = size + 1 + len(extra)` where `size` includes backend overhead (huffman adds its 512B table). `extra` (0-8B, up to 8+4·num for subblocks) is counted, so big side info must earn its keep.
- **Backend compression**: one fresh compressor per evaluation (no shared mutable state - this is what makes ThreadPool safe). v4 lzma uses `9|PRESET_EXTREME` (+ `preset_dict` when trained) to match `xz -9`.
- **Winner selection**: `if total < best_size` (strict) starting from `RAW`/`inf` - first (lowest TID) wins ties.
- **Container writing**: header, then per-block frames in order. Parallel paths reassemble by index first, so bytes never depend on thread scheduling.

Example (escape hatch with inspection - application code should prefer `rissa.*`):

```python
from deep_compress.compressor_v3 import compress_with_dict, decompress_with_dict
comp, hist, dict_bytes = compress_with_dict(
    data, backend="zstd", level=19, block_size=131072, use_dict=True, fast=False, max_workers=None,
)
print(hist)  # Counter({'SHUFFLE_4': 3, 'RAW': 1})
print(len(dict_bytes) if dict_bytes else 0)
assert decompress_with_dict(comp) == data
```

---

## 4. Transform System

### Transform registry

`TRANSFORMS_V2: dict[int, tuple[str, enc, dec]]` in `deep_compress/transforms_v2.py`. 19 entries: TIDs 0-17 plus 19 (TID 18 is experimental-only, see below).

### 19 current transforms

| TID | Name | Extra | Effect, with example |
|-----|------|-------|----------------------|
| 0 | `RAW` | `b""` | identity fallback. `enc(b"abc") -> (b"abc", b"")` |
| 1 | `DELTA` | `b""` | `out[i] = in[i]-in[i-1]`. `b"\x10\x11\x13" -> b"\x10\x01\x02"` (counters, ramps) |
| 2 | `XOR_DELTA` | `b""` | `out[i] = in[i]^in[i-1]` (near-duplicate bytes) |
| 3 | `DELTA2` | `b""` | delta-of-delta (linear ramps, sensor baselines) |
| 4 | `MTF` | `b""` | move-to-front: local repeats become small ints, mostly `0` (used after BWT) |
| 5 | `BWT_MTF` | `>I` primary | Burrows-Wheeler (radix to 256K, C prefix-doubling) + MTF. Skipped above 2048B in v2/v3 loops, 256K in v4 (use TID 16 there) |
| 6 | `SHUFFLE_2` | `b"\x02"` | 16-bit column transpose: `b"abcd"*4 -> cols(aa..)(bb..)` (16-bit samples) |
| 7 | `SHUFFLE_4` | `b"\x04"` | 32-bit transpose (ints/floats: high bytes group together) |
| 8 | `SHUFFLE_8` | `b"\x08"` | 64-bit transpose (doubles) |
| 9 | `DELTA_ZIGZAG` | `b""` | delta + zigzag `((s<<1)^(s>>7))&0xFF` maps `-1 -> 1` (Gorilla-style jitter) |
| 10 | `DELTA2_ZIGZAG` | `b""` | second-order + zigzag (timestamps) |
| 11 | `ORDER2` | `b""` | residual of predictor `2*prev - prev2` (text-like) |
| 12 | `BWT_MTF_RLE` | `>I` primary | BWT+MTF+RLE with unambiguous 4-zero marker `[0,0,0,0,N-4]` |
| 13 | `FLOAT_SPLIT` | `b"\x04"` | IEEE754 split into 4 byte-streams (needs `len%4==0`; sign/exponent stream compresses to ~16%) |
| 14 | `BIT_TRANSPOSE` | `b""` | 8x8 bit-matrix transpose per 8B chunk, self-inverse (bit-plane-separable data) |
| 15 | `SHUFFLE4_DELTA` | `b"\x04"` | composition `SHUFFLE(4)->DELTA`, costed as single-T (general `Cost(T1)+Cost(T2)` needed for a second pair) |
| 16 | `BWT_SUBBLOCK` | `>I sub_size + >I num + num×>I primaries` (`0xFFFFFFFF` = raw chunk) | 1M split into 4x256K BWT+MTF each, concatenated |
| 17 | `DICT_RESERVED` | `b""` | frozen identity stub: prototyped substitution never paid, TID kept so old files decode |
| 19 | `RLE` | `b""` | `>BH` value+count pairs, runs split at 65535 (5MB of `x` -> 231B pre-backend) |

```python
from deep_compress.transforms_v2 import delta_encode, shuffle_encode, bit_transpose_encode
delta_encode(b"\x10\x11\x13")      # b"\x10\x01\x02"
shuffle_encode(b"abcd"*4, 4)       # b"aaaabbbbccccdddd"
bit_transpose_encode(b"\x01\x02"*4)  # 8x8 bit transpose
```

### Experimental transforms

- TID 18 `RACD` (`TRANSFORMS_EXPERIMENTAL`, record-aligned column dictionary): ruled out on real text (apparent wins were a whitespace-normalization bug; fixed version loses to RAW on nci). Gated for future record-structured binary data, never tried by default MDL.
- Order-1 Huffman (`huffman_order1_encode_block`: 256 context trees): implemented, gated (header too large until validated on Silesia).
- Range pipeline (`bwt_range.py`): `RangeEncoder`/`RangeDecoder` drafted with carry renormalization; the BWT->RLE->MTF path currently Huffman-packs as scaffolding. Not default.

### Transform IDs

Integers on the wire (names are display-only; renaming a name never breaks a file, renumbering would). v4 adds special TIDs 99 (`XOR_PREV`: `b"XORP"+>I`, sequential mode only - disabled under ThreadPool/streaming by loud check) and 100 (`BIT_PLANE`). Unknown IDs raise `FormatError` on decode, never skipped.

### Extra metadata

`extra: bytes` carries per-block side info counted in MDL: BWT primaries (`>I`), shuffle stride (1B), subblock tables (`8+4·num` B, validated ≤255B total at write time - `EXTRA_LEN` is one byte). Decoders strictly bound-check every extra read (`EOFError` on truncation).

### Examples

```python
# text-like: BWT path (small blocks only)
from deep_compress.transforms_v2 import bwt_encode, bwt_decode_fast
bwt, primary = bwt_encode(b"banana")   # (b"nnbaaa", 3)
assert bwt_decode_fast(bwt, primary) == b"banana"

# columnar 32-bit: SHUFFLE_4 groups the shared high bytes
import struct
recs = b"".join(struct.pack("<I", 1609459200 + i) for i in range(1000))
from deep_compress.transforms_v2 import shuffle_encode, shuffle_decode
sh = shuffle_encode(recs, 4)
assert shuffle_decode(sh, 4) == recs
```

---

## 5. v4 Container Format

Full byte spec: `FORMAT.md` (and `public/spec.html`). Summary with exact constants:

- `MAGIC = b"RISA"` (`0x52 49 53 41`), `VERSION = 4` (frozen; v3 files carry 3, legacy v2 carries 2), `EXT = ".rissa"`. Legacy magics `DCM2`/`DCM3`/`DCMP` auto-delegate to the v2 decoder.
- `BACKEND`: `0=huffman, 1=zlib, 2=lzma, 3=zstd` (anything else: `FormatError`).
- v3 header: `MAGIC(4) VER(1) BACKEND(1) NUM_BLOCKS(4) BLOCK_SIZE(4) DICT_LEN(4) DICT?`
- v4 header: same with `DICT_LEN(4) DICT_ORIG_LEN(4) DICT_COMP?` (`DICT_COMP` is lzma-compressed).
- `NUM_BLOCKS = 0xFFFFFFFF` marks a **streaming frame** (normal decoders reject it with "use `decompress_stream`"; the stream decoder also reads pre-sentinel legacy streams).
- Block: `TID(1) EXTRA_LEN(1) ORIG_LEN(4) COMP_LEN(4) EXTRA? COMP`, all big-endian. (Outline aliases: `ORIG_LEN` is the raw length, `COMP_LEN` the payload length.)
- v2 legacy: `ORIG_LEN` is `>H` (max 65535B; oversize writes refused); huffman tables are 256x `>H` counts (scaled pre-tree when needed).

Example header, format v4 1M single block, zstd, no dict: `52 49 53 41 04 03 01 00 00 00 01 00 10 00 00 00 00 00 00 00`.

---

## 6. Backends

- **LZMA** (`lzma`, preset 9; v4 path uses `9|PRESET_EXTREME` + 64M dict + trained `preset_dict` to match `xz -9`): best ratio on text/image. Single-threaded per call (blocks parallelize in threads).
- **Zstd** (`zstandard`, default level 19; public levels 1-4 map to 3/6/19/22): best all-round. Shared-dict header support (`ZstdCompressionDict`), MDL-gated per file. Falls back to `zlib` if the package is missing.
- **zlib** (level 9; level 1 as the fast screen only): fastest portable, weakest ratio. Screen estimator family for lzma targets when zstd is absent.
- **Huffman** (pure order-0 + C pack/unpack, 512B table): dependency-free fallback. Counts above 65535 scaled monotonically pre-tree so both sides share the stored table. Refused for streaming (frames carry no frequency table). v4+huffman backend is a known pre-existing failure (CHANGELOG; tracked by a CI marker test).

### rANS status

**No rANS anywhere in the codebase.** `archive/rans.py` is retired. Do not cite rANS as shipped.

### Range coder status

`deep_compress/bwt_range.py` drafts `RangeEncoder`/`RangeDecoder` (12-bit probs, cache-carry renormalization, adaptive contexts) but the BWT->RLE->MTF pipeline currently Huffman-packs as a placeholder. Gated, experimental, not default, not benchmarked.

---

## 7. Entropy Coding

- `freq: list[int]` - 256 counts (`freq[65]` counts `A`). Stored as 256x `>H`; `_fit_freq_16` scales tables whose max exceeds 65535 (ceil, nonzero stays nonzero) so encoder/decoder trees always agree.
- `codes: dict[int, str]` - prefix codes from `build_codes(build_tree(freq))`, e.g. `65: "0"`. Single-symbol edge builds a 2-leaf tree.
- `padding: int` - 0..7 zero bits filling the last byte. C `unpack` rejects padding >7 or beyond payload bits (`ValueError`, never an over-read).
- `encoded: bytes` - MSB-first packed bits. Example: `huffman_encode_block(b"AAA")` -> 1 payload byte + table.
- `entropy: float` - Shannon `-sum(p log2 p)` via `huffman.shannon_entropy` (one C pass). Example: `b"a"*1000` ent 0.00 while Huffman spends 1.00 b/sym - the gap a future rANS/arithmetic coder would close.
- `bits_per_sym: float` - `len(comp)*8/len(data)`; every CLI run prints it next to entropy.

```python
from deep_compress.huffman import huffman_encode_block, huffman_decode_block, shannon_entropy
enc, freq, pad, codes = huffman_encode_block(b"abracadabra")
assert huffman_decode_block(enc, freq, pad, 11) == b"abracadabra"
print(shannon_entropy(b"abracadabra"))  # ~2.04 bits/symbol
```

---

## 8. Streaming

```python
from deep_compress.compressor_v3 import compress_stream, decompress_stream
with open("big.bin", "rb") as fin, open("big.rissa", "wb") as fout:
    compress_stream(fin, fout, block_size=131072, use_dict=False)   # huffman refused here
with open("big.rissa", "rb") as fin, open("big.out", "wb") as fout:
    decompress_stream(fin, fout)                                     # EOFError on truncation, never partial
```

- **Memory behavior**: O(block_size) plus at most one shared dict. `use_dict=True` buffers the first 1MB once to train the dict, then streams. Whole-file API peak RSS measured 134-154MB (input + output + backend contexts); streaming stays near `block_size` + backend window.
- **`block_size`**: the memory knob. 64K/128K default; 1M/4M for archives. The CLI `--stream` flag uses the same path.
- **Streaming API**: same per-block MDL (fast screen applies), frames carry TID/EXTRA_LEN/ORIG_LEN/COMP_LEN like normal blocks. `huffman` refused at write time (no frequency-table field exists); unknown TIDs/versions/backends raise `FormatError`; short reads raise `EOFError`.

---

## 9. CLI

```
rissa input.bin -o out.rissa [--block 65536] [--dict] [--fast] [--backend zstd] [--level N] [--stream]
rissa -d out.rissa -o restored.bin
rissa input.bin -o out.rissa --block 131072 --dict   # shared dict
python tools/rissa_tool.py gui                        # Tkinter GUI (Compress/Decompress/Copy log/Discord)
python tools/rissa_tool.py doctor                     # must show every HAS_C_*=True (else silent slow fallback)
python tools/rissa_tool.py logs                       # log file path for bug reports
```

- **Arguments**: `input` (`-` = stdin), `-o/--output` (required, `-` = stdout), `-d/--decompress`, `--block` (4096/16384/65536/131072), `--dict`, `--fast` (verified identical winners, ~3x), `--backend`, `--level`, `--stream` (constant-memory framing).
- **Examples**:
  ```bash
  rissa telemetry.bin -o tel.rissa --block 131072 --fast
  rissa -d tel.rissa -o tel_restored.bin
  rissa big.bin -o big.rissa --stream --block 131072   # larger than RAM
  rissa-tool.exe doctor                                # frozen build health
  ```
- Every run logs to `%LOCALAPPDATA%/rissa/logs/rissa.log` (exe-dir, then temp, fallback); crashes print the log path + Discord invite and exit 1. Native Win32 GUI (`gui_native/`, 80KB, same backend): `build.bat` with w64devkit.

---

## 10. Internal Architecture

- `compressor_v4.py` - v4 path: adaptive blocks, `_eval_block_v4` (serial + ThreadPool share it; XOR_PREV explicitly gated to sequential), `_write_block_v4` (validates `extra <= 255`), lzma dict training, TIDs 99/100. v4+huffman backend: known pre-existing failure, CI-tracked.
- `transforms_v2.py` - the 19-entry registry + codecs; C dispatch with Python fallback behind `HAS_C_*`; skipped candidates logged (`diag.py`), `RISSA_STRICT=1` re-raises.
- `huffman.py` - order-0 + `shannon_entropy` (home for the tools' entropy readout); order-1 experimental.
- `errors.py` - `RissaError`/`TruncatedError`/`FormatError` (builtin-compatible). `api_types.py` - `Backend` Literal, `BlockResult` dataclass. `diag.py` - skip-note policy.
- `cdc_dict.py` - CDC substitution (Rabin-Karp, `FE FF+idx` tokens, `FE FE` escapes), experimental. `bwt_range.py` - range scaffold, experimental. `gpu_shuffle.py` - needs `cupy-cuda12x`, untested track.
- `deep_compress/` also holds: `cli.py` (`rissa` entry), `test_roundtrip.py` (correctness gate: transforms, all backends, 200 fuzz, audit regressions; banner reads PASS / KNOWN-FAILURE / UNEXPECTED), `test_c_equivalence.py` (randomized C-vs-Python parity incl. malformed inputs), `bench_461.py` (single-run tables), `bench_463.py --reps` (medians, RSS, CPU%, baselines, JSONL), `download_corpora.py`, `ARCHITECTURE.md`, `BENCHMARK_SYSTEM.md`, `KNOWN_RESULTS.md` (standing truth table), `PHASE3_REPORT.md`.
- C extensions (`rissa/c_*.c`, `setup.py`; portable `-O3`, `RISSA_NATIVE=1` for AVX2): shuffle/bit/delta kernels + batch ports (generic shuffle+decode, float-split, delta2, xor, order2, d2zz, mtf, rle, BWT radix, huffman pack, stats/ngrams/CDC). MinGW lessons: never `O!`+`&PyTypeObject` (use plain `O` + manual check); size counting arrays for max(256, N+1).
- `benchmark_silesia.py`, `final_bench.py` - corpus harnesses. `archive/` - retired code, reference only.

---

## 11. Historical Versions

- **v1** (2026-08-31): Huffman order-0 + RLE baseline.
- **v2** (2026-09-01): per-block MDL over 9-16 transforms, 16K blocks, `MAGIC RISA`. Legacy limits kept: `ORIG_LEN >H` (oversize refused), `VERSION = 2` delegates from newer decoders.
- **v3** (2026-09-02): 64K/128K blocks, `compress_stream`/`decompress_stream`, 1MB-to-64KB shared dict (MDL-gated). The stable container the public API writes.
- **v4** (2026-09-03): 1M/4M adaptive, lzma `preset_dict`, `VERSION = 4` frozen, TIDs 99/100, ThreadPool.
- **v4.1-v4.3**: adaptive single-block, dict gate, early-stop; Silesia 11 ties + x-ray win; CDC correctly gated (not promoted).
- **v4.4-v4.5**: `PRESET_EXTREME` closes the xz gap to +32B; subblock BWT; range coder drafted (gated).
- **v4.6-4.6.1**: pure-C kernels (141-308x), timed benches, RLE TID 19, `rissa[arrow]` shim.
- **v4.6.2**: batch C ports, circular-import fix (was silently disabling all C), fast screening, v3 ThreadPool, audit hardening (sentinel, strict errors, subblock relayout).
- **v4.6.3**: review checklist - dead pool removal, `RISSA_STRICT`, v4 unification, portable builds, screening evidence (zstd-1 + top-4), rigorous bench.
- **v4.6.4**: library polish I (this document's structure), logo, no-em-dash policy. Same bytes by design.

---

## 12. Known Experimental / Deprecated Features

- `RACD` (TID 18, `TRANSFORMS_EXPERIMENTAL`): ruled out on real text, gated.
- `DICT_RESERVED` (TID 17): frozen identity stub, never better than RAW; TID kept for old files.
- CDC dictionary substitution, order-1 Huffman, range coder, GPU shuffle: implemented-but-gated tracks, not default, not benchmarked.
- BWT above 256K per chunk: stopgapped by `BWT_SUBBLOCK` (4x256K); true 1M+ SA-IS on hold (BWT already loses where tested).
- v4 `huffman` backend: broken pre-existing (truncated block), CI marker test tracks it; v2/v3 huffman paths roundtrip fine.
- Commented `No-Op` bypass and `max_block`/`force_dict` debug knobs: intentionally left in source, not shipped behavior.
- Deprecated prose: anything saying "16 transforms", "v4.4" as a version, or pointing at `archive/rans.py` is stale - this file and `FORMAT.md` are canonical.
