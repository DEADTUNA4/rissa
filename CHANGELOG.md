# Changelog — rissa

**https://rissa.web.app — Apache 2.0 — `rissa-compress`**

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
