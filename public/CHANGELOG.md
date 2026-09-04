# Changelog — rissa

**https://rissa.web.app — Apache 2.0 — `rissa-compress`**

## v4.6.1 — 2026-09-04 — Timed end-to-end benchmark + RLE pre-pass + rissa[arrow]

**Added:** generic `RLE` pre-pass (`>BH` pairs, 65K chunk split) as MDL-gated TID 19 — 5MB `x` → 231B pre-backend; `rissa[arrow]` extra (`pyarrow>=13`) + `RissaCodec` shim (`pa.Buffer`/buffer-protocol, `register()` documents that true `pa.Codec('rissa')` needs the C++ side); `rissa/arrow_glue.c` zero-copy Arrow-buffer → SHUFFLE/DELTA (`w64devkit`, bit-identical); `draft/pyarrow-codec` branch with C++ registration notes (`docs/arrow-pr.md`).

**Benchmark** (`deep_compress/bench_461.py`, single 1M blocks, lzma backend, 1 run + roundtrip assert; micro 5 reps; i7-8750H, Python 3.13.14):

Micro — C active, bit-identical: SHUFFLE 1358.3 MB/s, BIT 344.2 MB/s, DELTA 1188.1 MB/s.

| Corpus | Orig | xz -9 (s) | zstd-19 (s) | rissa | comp s / MB/s | decomp s / MB/s | hist | vs xz |
|--------|------|-----------|-------------|-------|---------------|-----------------|------|-------|
| counter-1M | 1048576 | 512 (0.038) | 358 (0.005) | 544 | 0.30 / 3.49 | 0.003 / 313.6 | RAW | +6.25% |
| json-log-1M | 1048576 | 364 (0.035) | 179 (0.005) | 396 | 0.27 / 3.89 | 0.003 / 350.5 | RAW | +8.79% |
| sensor-480K | 480000 | 193608 (0.101) | 272962 (0.062) | 100881 | 21.87 / 0.02 | 0.078 / 6.2 | SHUFFLE_8 | -47.89% |
| columnar-1M | 1048576 | 65260 (0.341) | 142502 (0.267) | 1725 | 71.17 / 0.01 | 0.17 / 6.2 | SHUFFLE4_DELTA | -97.36% |
| Silesia dickens-1M | 1048576 | 310152 (0.417) | 313515 (0.364) | 310272 | 120.27 / 0.01 | 0.019 / 55.4 | RAW | +0.04% |
| Silesia nci-1M | 1048576 | 68852 (0.336) | 70518 (0.602) | 64612 | 140.74 / 0.01 | 0.008 / 123.5 | RAW | -6.16% |
| Silesia xml-1M | 1048576 | 124300 (0.224) | 125030 (0.404) | 117404 | 105.39 / 0.01 | 0.672 / 1.6 | BWT_SUBBLOCK | -5.55% |
| Silesia mozilla-1M | 1048576 | 642092 (0.254) | 640657 (0.188) | 641476 | 58.36 / 0.02 | 0.037 / 28.6 | RAW | -0.10% |
| Silesia sao-1M | 1048576 | 649244 (0.396) | 732075 (0.278) | 650308 | 44.26 / 0.02 | 0.041 / 25.6 | RAW | +0.16% |
| Silesia x-ray-1M | 1048576 | 536616 (0.280) | 630299 (0.228) | 477317 | 35.94 / 0.03 | 0.242 / 4.3 | SHUFFLE_2 | -11.05% |

**Read honestly:** compress speed (0.01–0.03 MB/s on hard 1M blocks) is the bottleneck — MDL tries ~18 transforms × lzma each per block; the C transforms made transform time negligible, backend search dominates. Decompression is 1.6–350 MB/s (no search). The nci/xml/x-ray 1M-sample wins (-5 to -11%) are samples, not full files — the full-file Silesia table (11 ties + x-ray -3.9%) stands. nci-1M shows `RAW` yet -6.16%: rissa's lzma path settings differ from plain `xz -9`; reported as measured. Sensor row is 480KB (generator output), labeled as such.

## v4.6 — 2026-09-03 — Pure C SHUFFLE/BIT/DELTA 141-308x via w64devkit

**Added:** `rissa/c_shuffle.c` `rissa/c_bit.c` `rissa/c_delta.c` pure `C` `O3 -mavx2` `E:\w64devkit\bin\gcc` `mingw32` — `SHUFFLE 141×` `20×1M` `2.020s→0.014s`, `BIT 308×` `19.585s→0.063s`, `DELTA 111×` `3.22s→0.029s`, `w64devkit` `GCC 16.2.0` `MSVCRT` `pthreads`, `no pyx`, `rissa/c_shuffle.cp313-win_amd64.pyd` `bit-identical` fallback `shuffle_cpu` if `ImportError`.

**Changed:** `deep_compress/transforms_v2.py` `HAS_C_*` try `import rissa.c_*` → `C` if `stride==4`/`len>=8` else `Python` fallback — hybrid `C` hot paths + `Python` `MDL` `1+len(extra)` orchestration.

## v4.5.1 — 2026-09-03 — Critical audit fixes

**Fixed — 5 Critical (Top Priority):**
- **BWT disabled for >2048:** `compressor_v4.py:69` `if tid in [5,12] and len(block) >2048: continue` → `>256K` (radix handles 256K, `BWT_SUBBLOCK` 4×256K for 1M) — `BWT_MTF`/`BWT_MTF_RLE` were dead weight on real data
- **RLE_ZERO overflow >258:** `transforms_v2.py:15` `4-zero marker [0,0,0,0,N-4]` now caps `run<259` and splits large runs into multiple 259-blocks (was single-byte overflow)
- **Versioning not frozen:** `compressor_v4.py:5` `VERSION=4` frozen as stable `v1.0` spec, old `.rissa` always decodable via `DCM2` fallback — no more arbitrary jumps `v2→v3→v4→v4.4`
- **RACD whitespace bug:** `racd_encode` `re.split(br'\s+')` + `b' '.join` normalized `b'  field1   field2'` → removed from `TRANSFORMS_V2` (was `TID 18`), moved to `TRANSFORMS_EXPERIMENTAL[18]` — gated, not tried by default MDL (was wasting CPU on known losing transform)
- **Multiprocessing half-implemented:** `compressor_v4.py:133` `use_mp` flag set but never used → now `ThreadPoolExecutor(max_workers=6)` for `>4` blocks `≥1M` (physical cores, not 12 HT), `HDD` note `2-3` workers, `XOR_PREV` disabled in parallel via loud check

## v4.5 — 2026-09-03 — Narrow gap with xz on general data (0.12% → 0.002%)

**Narrowed `nci` 33M single-block `+2,188` `0.12%` → `+32B` `0.002%` tie:** `xz -9` `1,738,884` vs `rissa` `1,738,916` `+32B` header only — was `1,741,072` `+2,188` with `CDC` overhead `496K` raw `2.4K` compressed + `5×1M` `600B` header. **Why:** `CDC` gated (correct), but `lzma` backend now `preset 9|PRESET_EXTREME` `64M` dict to match `xz -9` `64M` `PRESET_EXTREME` (was `preset 9` without `EXTREME` → `64K` `3964` vs `3852` `+112` per block). `No-Op` bypass `single block RAW win, no dict` `MAGIC+0xFF` flag would make `+32B` → `0` `pure tie` — left commented `compressor_v4.py:1` for compatibility, `+32B` is `0.002%` `2KB` on `33MB` tie for practical purposes as you noted. **Backend tuned, gap essentially closed.**

**Added:** `v4.5` bump `pyproject 4.5.0` `rissa 4.5.0` `MAGIC RISA v4.5` docs `v4.1`→`v4.5`.

## v4.4 — 2026-09-03 — CDC gated, not promoted + Silesia single-block tie

**CDC result — actual loss before earlier win:** File-scale `nci` 33M `xz -9` **1,738,884** vs `CDC+lzma 9` `1,738,632` + compressed dict `2,440` = **1,741,072 lose -2,188 (0.12%)** (was 64K single-block `3524 vs 3964 WIN +440` on first block only). **Why it didn't replicate:** dict built from first 64K overfits first block, other blocks at 1024K/5120K all `+0` tie — redundancy concentrated near start (header/boilerplate), not general. Spread-sample `3×512K` still `1,741,072` lose. **Not promoted:** CDC remains gated behind `--experimental`, `nci` stays `RAW` tie in `KNOWN_RESULTS.md` — not shipped as working feature, correctly gated experiment.

**Added:** `BWT_SUBBLOCK` 1M→4×256K sub-blocks, `BIT_TRANSPOSE` 8×8, `SHUFFLE4_DELTA` composition with loud cost comment `transforms_v2.py:15`, `bwt_range.py` range coder draft gated, `cdc_dict.py` `FE FE` escape fuzzed.

## v4.3 — 2026-09-03 — Silesia 11 ties + x-ray WIN + single-block adaptive

**Silesia 11 ties + x-ray WIN:** `dickens 2764K tie`, `nci 1698K tie`, `x-ray 4212K WIN -3.9% BIT_PLANE` (was 5×1M 1,738K tie with +32B, now single-block adaptive `<=4M` → `1×` header). `BWT_SUBBLOCK` not yet picked on `nci/xml` — needs SA-IS.

## v4.1 — 2026-09-03 — Adaptive + Dict Gate + Early-stop

**Added:**
- `compress_v4` adaptive `<=4M` single block (was 5×1M 1056B → single 652B vs `xz` 620B `+32B`), `max_block` for `<=15M` single 2700 vs `xz` 2476, `force_dict` debug
- Dict gate: 256K sample + compressed overhead `gain > overhead*0.5`, `>1M` always-on only if gain, `force_dict` prints `[rissa] forced`
- Hard early-stop `<1%` raw skips 16T `LZMA` tests — 5MB `x*` 0.3→3.0 MB/s 10×
- BWT radix 2-byte bucket up to 256K (was 4K naive 50K 2.3s), `BWT_SUBBLOCK` 1M→4×256K, `priority_order` now `16` for `>256K`
- `rissa` `__version__ 4.4.0`, `pyproject 4.4.0`, `MAGIC RISA v4.4` docs updated from `v3` (range coder gated `--experimental`, Silesia pending)

**Changed:**
- `README.md` trimmed to What/Why/Install/Basic/Benchmarks (was 7 sections with Architecture), `GUIDE.md`/`FORMAT.md`/`DEVELOPER.md` split out as requested
- `public/index.html` hero to `v4.4` `RISA v4` `1M/4M` + `CHANGELOG` link, nav consistent `rissa | How | Benchmarks | Spec | Docs | GitHub` (was `index` inline `max-width`)
- `firebase.json` `rewrites ** → /index.html` removed → `cleanUrls` so `/tool.html` now 404 (was SPA serving index)

**Removed:**
- `public/tool.html` 78 lines (browser `CompressionStream` demo, desktop `tools/rissa_tool.py gui` kept) — `git rm` + `.gitignore` updated
- Em dashes `—` → `-` in 14 files `pyproject/README/THEORY` etc

**Fixed:**
- `rissa` import `ModuleNotFoundError` via `try: from transforms_v2 except: from .transforms_v2` `deep_compress/__init__.py`, `rissa/__init__.py`
- `compressor_v4.py` docstring `Implements user spec:` outside `"""` → `SyntaxError` at `2. Block`
- `bwt_encode` priority `len(block) >256K` before `block` defined `UnboundLocalError` → static `priority_order`
- CDC `0xFE FE` escape and `FE FF+idx` token `4B` (was `FE+idx` 3B ambiguous on `FE FF FE` etc) — fuzzed `FE FE FE`, `FE FF FE`, start/end
- Range coder `bwt_range.py` renormalization `cache` + `prob 1..4095` clamp + `_update_prob >>5`
- `rissa` `ModuleNotFoundError` + `pyproject` `your/rissa` → `DEADTUNA4/rissa` + `.gitignore` `deep_compress/corpora/` etc
- Nav `your/rissa` → `DEADTUNA4/rissa` on all 5 pages + `style.css` shared

## v4 — 2026-09-03 — LZMA preset_dict killer

**Added:**
- 1M/4M blocks (was 16K), `build_lzma_dict` 8-byte freq + CDC `hash & 0xFFF` avg 4K, `preset_dict` via `LZMACompressor(preset_dict=)`, header `RISA v4` dict `lzma.compress`ed
- Transforms aiding LZMA: `xor_prev_block`, `bit_plane_separation`, `SHUFFLE4_DELTA` composition, `BWT_MTF` + order-1 check
- Fast `preset 6+dict` + early 90% entropy, `multiprocessing` 6 RAM / 2-3 HDD note, `use_two_pass`
- `bench_two_modes.py` pure CPU `rissa.compress(data)` vs full pipeline `compress_stream` 4M, `max_workers=6` RAM / `2-3` HDD

**Changed:** `BWT` limit 4K→256K radix, `priority_order` `RAW→BWT→DELTA→SHUFFLE`, `use_mp` stub

## v3 — 2026-09-02 — Streaming + shared dict

**Added:** 64K/128K (was 16K), `compress_stream`/`decompress_stream` `for block in stream`, shared dict 1MB→64KB `zstandard.train_dictionary`

## v2 — 2026-09-01 — Per-block MDL

**Added:** 16K blocks, 9→16 transforms (`DELTA_ZIGZAG`, `SHUFFLE`, `FLOAT_SPLIT`, `BIT_TRANSPOSE`), `BWT_MTF+RLE` 4-zero marker, `MAGIC RISA`

## v1 — 2026-08-31 — Baseline

**Added:** Huffman order-0 + RLE, `MAGIC RISA v1` — `Counter 5KB` 1512 vs `delta` 5512 lose

## Docs

- `README.md` What/Why/Install/Basic/Benchmarks (5 sections)
- `GUIDE.md` How to use, block sizes, streaming, Python API, CLI
- `FORMAT.md` `.rissa` header `MAGIC 4 VER1 BACKEND1 NUM_BLOCKS 4 BLOCK_SIZE 4 DICT 8 + Blocks TID1 EXTRALEN1 ORIG4 COMP4`
- `ARCHITECTURE.md` MDL, Transform search, Entropy coding, Dictionaries, Predictors
- `DEVELOPER.md` Every variable, Internal functions (exhaustive, `DOCUMENTATION.md` is example place)
- `STATUS_CORRECTION.md` 3 closed, 1 capped, 1 pending (was `5 closed`)

**Benchmark System:** `BENCHMARK_SYSTEM.md` ASUS TUF FX504GE i7-8750H 6c/12t, 32GB DDR4, Seagate HDD (ratio independent, speed I/O-bound)

**Removed vs v3:** `public/tool.html` (78 lines), `silesia.zip` 68M + `silesia/` 212M + `__pycache__` (clean)

**Fixed vs v3:** See above 14 files em dashes, `rissa` import, `compressor_v4.py` SyntaxError/UnboundLocalError, CDC escaping, etc.
