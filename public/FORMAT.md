# Format — .rissa File Format

**MAGIC `RISA` v4 — https://rissa.web.app/spec.html — deterministic, versioned, streaming**

## Overview

```
File := MAGIC(4) VER(1) BACKEND(1) NUM_BLOCKS(4) BLOCK_SIZE(4) DICT_LEN(4) DICT_ORIG_LEN(4) DICT? [DICT_COMP]
        { Block }*
Block:= TID(1) EXTRA_LEN(1) ORIG_LEN(4) COMP_LEN(4) EXTRA? COMP
```

All integers big-endian `>I` / `>H`.

## Header

| Field | Size | Value |
|-------|------|-------|
| `MAGIC` | 4 | `0x52 49 53 41` `"RISA"` (was `DCM2`/`DCMP` legacy auto-migrated) |
| `VER` | 1 | `3` (64K/128K) or `4` (1M/4M adaptive, `RISA v4.4`) |
| `BACKEND` | 1 | `0=huffman` `1=zlib` `2=lzma` `3=zstd` |
| `NUM_BLOCKS` | 4 | `>I` number of blocks |
| `BLOCK_SIZE` | 4 | `>I` 4096, 16384, 65536, 131072, 1048576, 4194304 or `len(data)` for single |
| `DICT_LEN` | 4 | `>I` compressed dict length (0 if none) |
| `DICT_ORIG_LEN` | 4 | `>I` original dict length |
| `DICT_COMP` | var | `lzma.compress(dict, preset=9)` if `DICT_LEN>0` |

Example header for `v4.4` 1M without dict: `52 49 53 41 04 03 03 00 00 00 01 00 10 00 00 00 00 00 00 00 00 00 00`

## Blocks

| Field | Size | Note |
|-------|------|------|
| `TID` | 1 | Transform ID 0-16 |
| `EXTRA_LEN` | 1 | 0-2 |
| `ORIG_LEN` | 4 | `>I` original block length |
| `COMP_LEN` | 4 | `>I` compressed payload length |
| `EXTRA` | 0-2 | BWT primary `>H` 2B, SHUFFLE stride 1B `0x02/04/08`, else 0 |
| `COMP` | var | `backend(transform(block))` |

For single-block `<=4M` file, `NUM_BLOCKS=1` header overhead `4+1+1+4+4+8 + per-block 10 = 32B` (was 600B with 5×1M).

## Transform IDs

| TID | Name | Extra | When |
|-----|------|-------|------|
| 0 | `RAW` | `b""` | fallback |
| 1 | `DELTA` | `b""` | counters |
| 2 | `XOR_DELTA` | `b""` | near-duplicate |
| 3 | `DELTA2` | `b""` | linear ramps |
| 4 | `MTF` | `b""` | after BWT |
| 5 | `BWT_MTF` | `>H` primary | text ≤256K (radix) |
| 6 | `SHUFFLE_2` | `b"\x02"` | columnar 2B |
| 7 | `SHUFFLE_4` | `b"\x04"` | 32-bit |
| 8 | `SHUFFLE_8` | `b"\x08"` | 64-bit |
| 9 | `DELTA_ZIGZAG` | `b""` | Gorilla jitter |
| 10 | `DELTA2_ZIGZAG` | `b""` | timestamps |
| 11 | `ORDER2` | `b""` | `2*prev - prev2` |
| 12 | `BWT_MTF_RLE` | `>H` | BWT+MTF+RLE 4-zero marker |
| 13 | `FLOAT_SPLIT` | `b"\x04"` | IEEE754 4-stream |
| 14 | `BIT_TRANSPOSE` | `b""` | 8×8 bit matrix |
| 15 | `SHUFFLE4_DELTA` | `b"\x04"` | composition `SHUFFLE→DELTA` (single TID, single extra — see cost note) |
| 16 | `BWT_SUBBLOCK` | `>H sub_size + >H num + 2*num primaries` | 1M→4×256K sub-blocks |
| 99 | `XOR_PREV` | `b"XORP"+>I` | cross-block XOR (disabled in parallel/streaming, loud check) |
| 100 | `BIT_PLANE` | `b""` | bit-plane separation |

Cost for `TID 15` is currently `1+len(extra)` single-T MDL — general `T1→T2` should be `Cost(T1)+Cost(T2)+Cost(Data|T1,T2)` (`transforms_v2.py:15` loud comment).

## Metadata

- **Dictionary:** `DICT_COMP` is `lzma` compressed `64KB` from `build_lzma_dict` (8-byte freq or CDC `hash & 0xFFF`). Stored once, used as `preset_dict` for all blocks via `lzma.compress(..., preset_dict=dict)`. MDL-gated: only if `with+dict < without`.
- **Streaming:** `compress_stream(in, out, block_size=131072)` writes same header but `NUM_BLOCKS` known after first 1MB sample for dict. `xor_prev_block` disabled in `use_mp` to avoid silent wrong decode.
- **Compatibility:** `decompress_v4` auto-migrates `DCM2`/`DCMP` → `RISA`. `VERSION` bump for breaking changes.

## Compatibility

- `v3` (`MAGIC DCM2` 64K/128K) → `v4` (`RISA` 1M/4M) decompressor accepts both (`compressor_v4.py:decompress_v4` falls back to `compressor_v3`).
- Deterministic: sorted `TRANSFORMS_V2` iteration, no hash tie-break. Same input → same `.rissa`.

Source: `deep_compress/compressor_v3.py`, `compressor_v4.py`, `transforms_v2.py` — Apache 2.0.
