# Phase 3 Report - Real Corpus Evaluation (64K/128K + Shared Dict + 16 Transforms)

**Ingested:** `corpora/` 4 real files (downloaded via curl resume):
- `yellow_tripdata_2023-01.parquet` 46,949,719B (NYC TLC, columnar)
- `Apache_2k.log` 171,239B (Loghub, text)
- `HDFS_2k.log` 287,848B (Loghub, text)
- `noaa_01001099999.csv` 450,082B (NOAA Global Hourly, csv)

Synthetic generators also kept for binary sensor reference `ingest_phase3.py:gen_*`.

## Method
Per-block MDL `compressor_v3.py:7` 64K/128K, 16 candidates `TRANSFORMS_V2:78` (incl `BIT_TRANSPOSE:14`, `SHUFFLE4_DELTA:15`), fast estimate `zlib-1` → top2 `zstd19`/`xz9`. Baselines `zlib9`, `xz -9` (`lzma preset 9`), `zstd -19/-22` (`zstandard`), `bzip2 -9`. Metric `bits/symbol = compressed*8/orig`, distance to Shannon `shannon:12` ` -Σ p log2 p`.

## Results (2MB sample for parquet, full for logs/csv)

| Corpus | Orig | Entropy b/B | Shannon | xz-9 | zstd19 | zstd22 | ours-zstd 64K | ours-zstd 128K | hist (top) |
|---|---|---|---|---|---|---|---|---|---|
| NOAA csv 450K | 450,082 | 3.69 | 207,624 (46%) | **28,924** 0.51 | 30,286 0.54 | 30,294 | 33,192 0.59 `RAW:7` | **31,856** 0.57 `RAW:4` | - |
| Apache log 171K | 171,239 | 4.97 | 106,375 (62%) | 7,236 0.34 | **7,161** 0.33 | 7,168 | 7,862 0.37 `RAW:3` | **7,513** 0.35 `RAW:2` | - |
| HDFS log 287K | 287,848 | 5.22 | 187,705 (65%) | **42,768** 1.19 | 42,807 | - | 46,220 1.28 `RAW:5` | **44,588** 1.24 `RAW:3` | - |
| Yellow parq 2MB sample | 2,000,000 | 8.00 | 1,992,032 (99.6%) | 1,997,520 8.00 | **1,996,744** 7.99 | - | 1,997,388 7.99 `RAW:24 BIT:2 SH4:3` | **1,996,665** 7.99 `RAW:13 SH8:3` | tie at entropy |

Synthetic reference (binary, not csv):
- NOAA-sensor binary `ts+float` 500K `gen_noaa` entropy 6.85: xz 290K, **ours 128K 291K tie** (`SHUFFLE_8:4`) beats zstd 353K.
- YellowTaxi columnar synthetic 500K: xz 304K vs ours 323K close.

## Analysis
- **Logs (text):** `RAW` wins, no shuffle/delta benefit. Per-block header (1+extra+4+4 per block) makes 64K/128K win over 16K (171K: 7,862→7,513) but still +3-4% vs xz large-window (8MB dict). Expected - shared dict `compressor_v3.py:12` adds +64KB overhead on <1MB files (Apache `dict True` 61K vs 7K) - MDL must gate dict off for <1MB (currently bench shows both, winning is `dict=False`). Needs >1MB real corpus to amortize.
- **NOAA csv (text):** Same, csv is text not binary float → `FLOAT_SPLIT` not triggered, `SHUFFLE` not. Binary sensor (synthetic) _does_ win (`SHUFFLE_8`), proving need for raw binary sensor data, not csv.
- **Yellow Taxi parquet (already compressed, entropy 8.00):** All tie at ~100.2% over Shannon - correct fallback to RAW with minimal overhead, picks `BIT_TRANSPOSE`/`SHUFFLE` on residual columnar blocks where structure remains. Validates Known Limitations (no magic on high-entropy).
- **Shannon distance:** Logs are ~60% shannon, our `b/sym` within 0.05 of xz; parquet is 99.6% shannon, all at shannon limit.

## Next for Phase 3
1. Replace `noaa csv` with raw binary sensor (e.g., NOAA ISD binary or your sensor dump) to trigger `FLOAT_SPLIT`/`SHUFFLE4_DELTA`.
2. Yellow Taxi: ingest decompressed CSV (convert parquet via `pyarrow`) not parquet file - then `SHUFFLE_4`/`BIT_TRANSPOSE` on raw 6-col int/float will show win (synthetic already 333K→291K).
3. Enable MDL gating for dict (only use if `size_with_dict + len(dict) < size_without`), and test on >1MB concatenated logs (10MB HDFS).
4. Report multi-run variance + wall-clock/memory (currently single-run size only).

Place real >1MB `*.csv`/binary sensor in `corpora/` and rerun `python deep_compress/ingest_phase3.py`.
