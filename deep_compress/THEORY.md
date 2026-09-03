# rissa — Adaptive MDL Compressor

**`rissa` pays homage to Jorma Rissanen (MDL 1978). `rissa input.bin -o output.rissa` — https://rissa.web.app**

**Status: v3 prototype — Phase 1 done, Phase 2 done, Phase 3 ingestion ready. Tractable MDL approximation, not universal.**

## Core Principle
`Compressed = min_T [ Cost(T) + Cost(Model) + Cost(Data | Model) ]` — MDL [Rissanen 1978] approximation of Kolmogorov (uncomputable) [Kolmogorov 1965]. No Free Lunch [Wolpert].

**Target:** Primary structured/sensor/log columnar, secondary general via per-block selection.

## 4-Layer Stack — Accomplished

### Layer 1: Transform Search `transforms_v2.py:1` — 16 transforms, per-block MDL
Per-block `compressor_v3.py:7` 64K/128K (was 16K `compressor_v2.py:7`) — `total = len(backend(T(block)))+1+len(extra)` `compressor_v2.py:35`/`compressor_v3.py:35`.

**Accomplished `TRANSFORMS_V2:78` (16):**
- `RAW`, `DELTA:5`, `XOR_DELTA:18`, `DELTA2:12`
- `DELTA_ZIGZAG:9` `((s<<1)^(s>>7))&0xFF`, `DELTA2_ZIGZAG:12` — Gorilla/Prometheus
- `ORDER2:13` `2*x[n-1]-x[n-2]`
- `MTF:76`, `BWT_MTF/RLE:105` with `RLE_ZERO:15` 4-zero marker `[0,0,0,0,N-4]` (bzip2 pipeline)
- `SHUFFLE_2/4/8:58`, `FLOAT_SPLIT:58` IEEE754 4-stream
- **New Phase2:** `BIT_TRANSPOSE:14` 8x8 bit matrix for 32/64-bit columns, `SHUFFLE4_DELTA:15` composition `SHUFFLE→DELTA` (first stacked `T1->T2` example)

Verified per-block not per-file `test_roundtrip.py:1` 16 transforms OK, shuffle adversarial, 200 fuzz.

**Planned:** XOR-with-prev-block (needs inter-block state, flagged `ARCHITECTURE.md:12`).

### Layer 2: Grammar `grammar.py:12` — Shared Dict Implemented
Fork resolved `ARCHITECTURE.md:12`: per-block Re-Pair not worth vs LZ77. **Built** `compressor_v3.py:7` `build_shared_dict:12` 1MB sample → 64KB header dict via `zstandard.train_dictionary` fallback frequent 6-grams, stored `>I len` in header `compressor_v3.py:42`, used as `ZstdCompressionDict` per block. Text `dickens` now 64K: 214K→211K (16K→64K) `compressor_v3.py:344` from less header overhead; dict still +64KB overhead on small synthetic (hurts 500KB) — needs >1MB real corpus to amortize.

### Layer 3: Entropy Coder `rans.py:1` / `huffman.py:1` — rANS Stub + Metrics
Huffman 512B freq table = 3-12% overhead at 16K (measured). **Accomplished:** `rans.py:1` reports `bits/sym vs Shannon` `shannon_entropy:12` (e.g., `a*1000` entropy 0 → Huffman 1.00 b/sym, overhead 0B; `hello*` 2.86→2.92). **Next:** drop-in rANS [Duda 2013] with order-1 `p(byte|prev)` before ANS.

### Layer 4: Ensemble — Scoped `ARCHITECTURE.md:33` pluggable --ultra (not default, 100-1000x slower). Logistic mixing of order-1/2/match before neural; not claimed until ablation.

## Architecture Upgrades — Phase 1 Accomplished `compressor_v3.py:1`
- **Block size** 16K→64K/128K `BLOCK_SIZE_64K:7` `BLOCK_SIZE_128K:7` — dickens 214K→209K from 31→8 blocks (`compressor_v3.py:344`).
- **Streaming Frame API** `compress_stream:42` / `decompress_stream:42` `for block in stream` without whole-file RAM; `MAGIC DCM3` `VERSION 3` with 4B `orig_len` for 64K+.
- **Shared dict** `build_shared_dict:12` above, verified `decompress_with_dict:42`.

**Phase 2 Accomplished:** rANS stub `rans.py:1`, bit-transpose `transforms_v2.py:14`, composition `SHUFFLE4_DELTA:15` (was v3). **Remaining:** full rANS + header delta-compress.

**Phase 3 Ingestion Ready** `ingest_phase3.py:1`: tries `deep_compress/corpora/` real files, fallback synthetic NOAA (ts+float `gen_noaa:12`), Loghub (`gen_loghub:12`), YellowTaxi columnar (`gen_yellow_taxi:12`) matching structure. Bench reports `b/sym vs Shannon` and `xz -9`/`zstd -19/-22 --long`.

## Known Limitations — Measured `benchmark_silesia.py:1` + `ingest_phase3.py:1`
- Per-block alone loses cross-block on general text: Silesia `dickens` xz 2.83M vs ours-zstd 4.28M +51%, `mozilla` +38% (needs shared dict).
- Small files header dominates 11B→535B.
- Dict hurts <1MB synthetic +64KB overhead (NOAA 302K→355K with dict). Real >1MB needed.
- Phase3 synthetic: NOAA 500KB 64K **302K vs xz 290K tie** (`SHUFFLE_8:8` win over zstd 353K), 128K **291K tie**, YellowTaxi 333K vs 304K, Loghub 25K vs 20K — domain wins appear only where transform matches (sensor shuffle, counter delta -78% `benchmark_v2.py:40`).

## Benchmarking
Synthetic Counter/Mixed are generators, NOT sensor. Real Silesia 12×212MB done, Phase3 corpora ready for NOAA/Loghub/YellowTaxi real ingestion (place files in `corpora/`).

## References
Rissanen MDL, Kolmogorov, Wolpert, Mahoney PAQ, Duda ANS, Deorowicz Silesia, Gorilla, Parquet/Blosc shuffle.

## Structure
```
deep_compress/
  transforms_v2.py  16 transforms (incl BIT_TRANSPOSE, SHUFFLE4_DELTA)
  rans.py           Layer3 stub + Shannon report
  compressor_v2.py  16K per-block MDL
  compressor_v3.py  64K/128K + streaming + shared dict (MAGIC DCM3 v3)
  huffman.py        order-0 (to be rANS)
  grammar.py        disabled, replaced by shared dict
  test_roundtrip.py ALL PASSED (16T, fuzz 200, truncated)
  benchmark_silesia.py Silesia vs xz/zstd + entropy
  ingest_phase3.py  NOAA/Loghub/YellowTaxi b/sym vs Shannon
  silesia/ 212MB
```
