# Problems Found — rissa

**https://rissa.web.app — https://github.com/DEADTUNA4/rissa — Apache 2.0**

This is the exhaustive list of problems found during v1-v4.4, with status and fix. Updated as we go.

## High — Correctness / Trust (must fix before default)

| # | Problem | Impact | Status | Fix |
|---|---------|--------|--------|-----|
| 1 | **CDC token escaping `0xFE` literal → silent corruption** | Landmine in `cdc_dict.py` feature about to be benchmarked | **Fixed** `cdc_dict.py:1` `FE FE` escape `FE FF+idx` `4B` fuzzed `FE FE FE`, `FE FF FE`, start/end | `cdc_dict.py` |
| 2 | **Range coder renormalization unfinished** | Highest-risk code, `bwt_range.py:1` `encode_bit`/`decode_bit` simplified | **Fixed** `cache` + `prob 1..4095` clamp + `_update_prob >>5` — still gated `--experimental` | `bwt_range.py` |
| 3 | **BWT stub at 1M+ blocks** | `bwt_encode` cap `4K` → `256K`, but `1M` is default block size → live code, not future TODO | **Capped** 256K closed, `BWT_SUBBLOCK:16` 4×256K handles 256K-1M, **1M+ still stubbed** needs `SA-IS` 200-300 lines `array('I')` | `transforms_v2.py:12` |
| 4 | **5MB `x*` canary `2.3×` loss to `xz -9`** | `1M` 5 blocks `1492` vs `xz 892` `+67%` → header overhead inflating every loss | **Fixed** adaptive `<=4M` single block `924` vs `892` `+32B` `3.5%` + hard early-stop `<1%` `0.3→3.0 MB/s` 10× `compressor_v4.py:1` | `compressor_v4.py` |
| 5 | **Silesia `nci`/`xml` thesis test pending** | Core claim `wins on structured` not validated, 11 ties proxy `RAW` not informative | **Re-run done** `nci` 33M single `1,738,916` vs `xz 1,738,884` tie `+32B` `RAW` wins all 18/18 dump, `x-ray` `BIT_PLANE` win `-3.9%` is real win (see `KNOWN_RESULTS.md`) — still **1 win / 11 ties**, not `beats xz` | `silesia/` 68M re-downloaded from `E:\Documents\Rombil\silesia.zip` |
| 6 | **`silesia.zip` deleted for clean** | Self-inflicted 68MB re-download on HDD 3KB/s, delayed most important open question | **Acknowledged** `STATUS_CORRECTION.md:1` `3 closed, 1 capped, 1 pending` — keep `silesia/` gitignored not deleted | `.gitignore` |

## Medium — Worth resolving

| # | Problem | Status |
|---|---------|--------|
| 7 | **Composition cost model `SHUFFLE4_DELTA:15` shipped as single-T** `1+len(extra)` vs general `Cost(T1)+Cost(T2)+Cost(Data\|T1,T2)` not answered, just sidestepped for one hardcoded pair | **Loud comment** `transforms_v2.py:15` + `compressor_v4.py:12` explaining what would need changing for second pair |
| 8 | **`xor_prev_block` vs `compress_stream` / `use_mp`** `prev_block_raw` not shared → silent wrong decode (not error) | **Fixed** `compressor_v4.py:12` loud check `if use_mp: skip TID 99` + comment, streaming `xor_prev_block` disabled |
| 9 | **`BWT_SUBBLOCK` concatenation overhead** `4×256K` may add overhead for zero benefit vs plain 1M | **Measured** `nci` 1M `BWT_SUBBLOCK` 4525 vs `RAW` 3965 lose, not yet default for `>4M` — hold off until MDL dump shows win |
| 10 | **Small-file header `512B` at 16K =3%** | **Fixed** `16K→1M` `0.05%` at 1M, `32B` at `<=4M` single, `rANS` stub `rans.py:1` reports `bits/sym` vs Shannon |
| 11 | **Placeholder links `your/rissa`** in `README.md` `pyproject.toml` `public/*.html` | **Fixed** `your/rissa` → `DEADTUNA4/rissa` 14 files, `pyproject` `Repository`/`Issues` |
| 12 | **Nav bar weird `index.html` inline `max-width:980px` vs others CSS `nav{}`** | **Fixed** `public/index.html:1` `nav{display:flex...}` + `nav a.active` consistent, 5 pages `rissa \| How \| Benchmarks \| Spec \| Docs \| GitHub` |
| 13 | **SPA rewrite `** → /index.html` made `/tool.html` still viewable (200 not 404)** | **Fixed** `firebase.json:1` `rewrites` removed → `cleanUrls` so `/tool.html` now `404` |
| 14 | **Em dashes `—` in 14 files** `pyproject/README/THEORY` etc | **Fixed** `—` `–` → `-` via `fix` script 14 files |
| 15 | **`rissa` import `ModuleNotFoundError` `from transforms_v2`** | **Fixed** `try: from transforms_v2 except: from .transforms_v2` `deep_compress/__init__.py` `rissa/__init__.py` |
| 16 | **`compressor_v4.py` docstring `Implements user spec:` outside `"""` → `SyntaxError` at `2. Block`** | **Fixed** `"""` wrap |
| 17 | **`bwt_encode` priority `len(block) >256K` before `block` defined `UnboundLocalError`** | **Fixed** static `priority_order` |
| 18 | **`silesia.zip` 68M + `corpora/*.parquet` 46M tracked as untracked** | **Fixed** `.gitignore:1` `deep_compress/silesia/` `deep_compress/corpora/` etc |
| 25 | **`THEORY.md` §8 rANS "gated `--experimental`" overstates like README did** | **Open** — needs the same correction README just got: range path is Huffman-placeholder scaffolding (`bwt_range.py:169-171`), no rANS implemented anywhere |
| 26 | **`deep_compress/THEORY.md:17` stale count + wrong TID numbers** | **Open** — says `(16)` with `DELTA:5`, `XOR_DELTA:18`, `DELTA2:12`; actual registry is 19 TIDs (0–17 + 19, 18 experimental) with `DELTA=1`, `XOR_DELTA=2`, `DELTA2=3`. Same stale-count class as the README `16T` fix; no doc currently claims 18-as-active (verified) |
| 28 | **THEORY.md needs full accuracy pass, not one-at-a-time patches** | **Open — decided: schedule dedicated pass** - gut-check sampling found 5+ confirmed issues in one 121-line file: (a) s4 "Replaced by rANS" states aspiration as fact (same class as s8 #25); (b) s3 points at dead `deep_compress/rans.py:12` (file retired to `archive/`); (c) s5 x-ray numbers `4525 vs 3965` are actually nci numbers (measured x-ray64K: BWT_MTF `36088` vs RAW `36172`); (d) s10 cost-comment pointer `transforms_v2.py:15` is actually line 464; (e) footer "version-sorted v4.4 latest first" stale (latest v4.6.1). Verified still-correct: s1 19 transforms, s9 DELTA `4881 vs 3965` (includes +1 TID byte MDL accounting), s11 cdc params, all referenced files exist. Two independent finds in short order => assume more; do one end-to-end pass as done for README |
| 27 | **v4.6.1 bench: rissa lzma path uses `9|PRESET_EXTREME`, baseline plain `preset=9`** | **Resolved (mechanism proven, not a transform win)** - controlled same-input test on nci-1M: plain `68852` vs extreme `64580`; rissa stored `64612` = extreme `+32B` header. The -6.16% is 100% flag effect, 0% transform. Fair baseline for the lzma path is `xz -9e`, against which nci-1M is a +32B tie. Decomposition at same preset (all reversible-verified): xml `119264` vs `124300` (-4.05% transform), x-ray `479308` vs `536616` (-10.68%), sensor `100860` vs `193608` (-47.9%), columnar `1696` vs `65260` (-97.4%) - all transform-confirmed |

## Low — Nice to have, hold off

| # | Problem | Note |
|---|---------|------|
| 19 | ** `tools/rissa_tool.py` browser `tool.html` demo used `CompressionStream` `deflate` placeholder, not real `rissa` MDL** | Removed `public/tool.html` 78 lines, desktop `tools/rissa_tool.py gui` kept (real `rissa`), `firebase.json` clean |
| 20 | ** `order-2` context mixing `256*256` array memory `16M` entries** | Hold off — `order-1` already gated, `BWT` not winning at 64K so order-2 won't move `nci` (per `nci` dump `RAW` wins all 18) — deprioritized below `SHUFFLE` stride detection |
| 21 | ** `SA-IS` for 1M+ BWT `200-300` lines `array('I')` `memoryview`** | Hold off — `BWT` loses at 64K `4525` vs `3965`, so unlocking at 1M+ not proven to matter until MDL dump shows `BWT` near `RAW` |
| 22 | ** Custom entropy `rANS` backend vs `lzma` `zstd`** | Hold off — `11/12` Silesia ties at transform layer, custom entropy optimizes non-winning part |
| 23 | ** Auto stride detection `SHUFFLE`/`FLOAT_SPLIT` `2/4/8`** | Next real lever — `x-ray` win via `BIT_PLANE`, synthetic columnar `-80%` `SHUFFLE`, but fixed `2/4/8` only helps if record width known |
| 24 | ** Docs still in `v3` (`MAGIC RISA v3` `64K/128K`)** | **Fixed** `RISA v4` `1M/4M` + 17 TIDs `BWT_SUBBLOCK` `DICT` `XOR_PREV` `BIT_PLANE` + copy buttons `public/spec.html:1` `FORMAT.md:1` |

## Benchmark System

**ASUS TUF FX504GE** i7-8750H 6c/12t @2.2GHz, 32GB DDR4, Python 3.13.14, Seagate ST2000LM007 2TB HDD (files on HDD, ratio independent, speed may be I/O-bound, multiprocessing 12 threads max 6 RAM / 2-3 HDD) — `BENCHMARK_SYSTEM.md:1`

**Current honest status (single source of truth `deep_compress/KNOWN_RESULTS.md:1`):** **1 real win** `x-ray` `BIT_PLANE` `-3.9%` (16-bit medical) + **2 synthetic wins** `columnar -80%` `sensor -35%` **(synthetic)** — synthetic labeled, not real. **11 ties** on Silesia general structured/scientific, all `RAW` full 18/18 dump (including `FLOAT_SPLIT` offsets 0-7 all lose `+1700` — correctly loses because `nci` is text `SDF` `"2.0000"` not binary `IEEE754`, so `FLOAT_SPLIT` scrambles, not misaligned). **Truer claim:** wins on bit-plane separable, ties on general structured — invest in `RACD` per-column `0-7` sweep (all 16 cols win `78-96%` reduction, `4.0%` remaining = `96%` win, `21.6%` remaining = `78%` win — `4.0%` is huge win, not fail).

**Benchmark sorting:** `public/benchmarks.html:1` version history latest first `v4.4` `v4.2` `v4` `v3` `v2` `v1` — `v4` Pure CPU `JSON 3762` + Real Corpora tables **inside `v4` details** (was in front, now inside).

## False Leads Appendix — Most Important: RACD

**RACD apparent win throughout development was caused by whitespace-normalization correctness bug; once fixed, loses to RAW on nci. Kept as `--experimental` for future record-structured binary data, not promoted.**

- **Mechanism:** `re.split(br'\s+', line.strip())` + `b' '.join` silently changed `b'  field1   field2'` (2+3 spaces) → `b'field1 field2'` (1 space) — `32` cols `95,160` vs `65,536` raw `+45%` but `lzma` `3,556` vs `3,964` win `+408` *because* whitespace collapsed, not because column transpose helped. Correct `re.split(b'(\\s+)')` preserving `32` cols with delimiters gives `95,160` `+45%` raw and `7,421` vs `3,965` lose.
- **How surfaced:** Deliberate correctness check prompted by general principle `does field-split preserve exact delimiter bytes, or does it normalize/collapse whitespace?` — not by test failing. Tested with `b'  field1   field2  \n'` irregular spacing, expected `FAIL` but got `PASS` via `b""` early return `len(data) <1024`, then larger `6,700` lines `300` with `1,714` lines `16` cols showed `RACD` `7421` vs `3965` lose once fixed.
- **Went to official on live public site before being caught:** `THEORY.md:1` `RACD Theory — OFFICIAL` `file-scale 33M 23,383,582 → 1,380,592 win 20.6%` pushed `30147f9` to `https://github.com/DEADTUNA4/rissa` and `https://rissa.web.app` as `official` — `23,383,582` was `22.3M` transposed intermediate not `33M` file `33,553,445`, direct `lzma` not `compress_v4` MDL `1+len(extra)` `>I` `TID 18` vs 17, no `decompress_v4(comp)==data` roundtrip, `18.7%` vs `20.6%` math mismatch. Reverted `cb6e977` to gated `3 closed, 1 capped, 1 pending`.

**Lesson:** `RACD` `16/16` columns `78-96%` reduction (`4.0%` remaining = `96%` win) rechecked with `reduction = 1-comp/raw` consistently — `4.0%` is huge win, not `4.0%` fail — but whole `1M` `14.7%` and `33M` `20.6%` were `direct lzma` wins, not `compress_v4` `MDL` wins. Keep `RACD` gated until `33M` `compress_v4` `TID 18` `0-7` sweep `>I` `1+len(extra)` + roundtrip on `33M` shows win.

All problems above are tracked here — this file is the `problem.md` you asked for.
