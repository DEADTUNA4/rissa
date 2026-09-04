# Draft PR: Register `rissa` as a pyarrow/Arrow codec — DO NOT OPEN YET

Target: `apache/arrow` (or `pandas-dev/pandas` parquet path).
Branch in this repo: `draft/pyarrow-codec` (pushed, ready to adapt).

## Proposed title

> [DRAFT] Codec: register `rissa` columnar codec (Rissanen MDL, SHUFFLE-first)

## Proposed body

`rissa` is an Apache-2.0 context-selecting compressor aimed at the
exact data Arrow holds: fixed-width numeric columns, sensor streams,
logs. Per-block MDL over 19 reversible transforms (`SHUFFLE_2/4/8`,
`DELTA_ZIGZAG`, `FLOAT_SPLIT`, `BIT_TRANSPOSE`, generic `RLE`, …),
`MAGIC RISA v4`, deterministic, streaming.

Measured (ASUS TUF FX504GE, i7-8750H, Python 3.13, `xz -9` baseline):

| Corpus | xz -9 | rissa | Result |
|---|---|---|---|
| Silesia x-ray 8.2M (real) | 4385K | 4212K `BIT_PLANE` | WIN -3.9% |
| Silesia other 11 files | — | +32B each | 11 ties |
| Columnar 3.6M (synthetic) | 204K | 39K `SHUFFLE_8` | WIN -80% |
| Sensor 6M (synthetic) | 1610K | 1038K `SHUFFLE` | WIN -35% |

Pure-C hot paths (`w64devkit` GCC 16.2, `-O3 -mavx2`):
`SHUFFLE` 141×, `BIT_TRANSPOSE` 308×, `DELTA` 111× vs CPython loops,
bit-identical, `HAS_C_*` fallback to Python.

This draft proposes:

1. `arrow::util::Codec::RegisterCodec("rissa", ...)` wiring
   (`rissa/arrow_glue.c` in this repo shows the zero-copy
   Arrow-buffer → transform pointer path, buffer-protocol, no input copy).
2. Python surface: `pip install rissa[arrow]` →
   `from rissa.arrow import RissaCodec, register` (same
   `compress`/`decompress` shape as `pa.Codec`; true
   `pa.Codec('rissa')` needs this C++ side merged).
3. Round-trip + fuzz harness (`deep_compress/test_roundtrip.py`:
   19 transforms + 200 random + truncated/corrupted).

Seeking maintainer guidance on: preferred codec-ID registration
path, whether a `pa.Codec`-compatible Python shim is acceptable as
a first step, and IPC/parquet conformance tests to run.

## Checklist before opening

- [ ] Fork `apache/arrow` (or target `pyarrow` python-only shim first)
- [ ] Rebase `draft/pyarrow-codec` onto fork
- [ ] `gh pr create --draft --repo apache/arrow --title ... --body-file docs/arrow-pr.md`
- [ ] Link back to `https://github.com/DEADTUNA4/rissa` + `https://rissa.web.app/benchmarks.html`

## Why draft, not ready

`pa.Codec` has a closed codec list (`gzip/bz2/brotli/lz4/zstd/snappy`)
with no runtime registration — a Python-only package *cannot* make
`pa.Codec('rissa')` work. Claiming otherwise would be dishonest.
This draft is the intent signal + the zero-copy glue, nothing more.
