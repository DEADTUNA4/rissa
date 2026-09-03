# Changelog — rissa

**https://rissa.web.app — Apache 2.0**

## v4.1 — 2026-09-03 — Adaptive single-block + dict gate + early-stop
- `compress_v4` adaptive: `<=4MB` single block (was 3 blocks for 2.9MB JSON 1056→652), `max_block` for 15MB single 15M block 2700 vs xz 2476
- Dict gate: 256K sample + compressed overhead `gain > overhead*0.5`, `>1MB` always-on only if gain, `force_dict` debug
- Hard early-stop: `<1%` raw skips 16T LZMA tests — 5MB `x*` 0.3→3.0 MB/s 10×
- BWT radix 2-byte bucket up to 256K (was 4K), SA-IS stub for 1M+
- `rissa` `__version__ 4.1.0`, `pyproject 4.1.0`

## v4 — 2026-09-03 — LZMA preset_dict killer
- 1M/4M blocks (was 16K), `build_lzma_dict` 8-byte freq + CDC chunks, `preset_dict` via `LZMACompressor(preset_dict=)`, header `RISA v4` dict compressed
- Transforms aiding LZMA: `xor_prev_block`, `bit_plane_separation`, `SHUFFLE4_DELTA` composition, `BWT_MTF` + order-1 check
- Fast `preset 6+dict` + early 90% entropy, `multiprocessing` 6 RAM / 2-3 HDD note, `use_two_pass`

## v3 — 2026-09-02 — Streaming + shared dict
- 64K/128K (was 16K), `compress_stream`/`decompress_stream` for `for block in stream`, shared dict 1MB→64KB `zstandard.train_dictionary`

## v2 — 2026-09-01 — Per-block MDL
- 16K blocks, 9→16 transforms (`DELTA_ZIGZAG`, `SHUFFLE`, `FLOAT_SPLIT`, `BIT_TRANSPOSE`), `BWT_MTF+RLE` 4-zero marker, `MAGIC RISA`

## v1 — 2026-08-31 — Baseline
- Huffman order-0 + RLE, `MAGIC RISA v1`

See `deep_compress/THEORY.md` and `deep_compress/BENCHMARK_SYSTEM.md` (i7-8750H 6c/12t, 32GB, HDD).
