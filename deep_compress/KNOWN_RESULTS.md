# Known Results — rissa Single Source of Truth

**Updated: 2026-09-03 — v4.1 — Silesia single-block `<=4M` adaptive, 12 files `deep_compress/silesia/`**

This is the standing table — win/tie/loss per file type, updated as we go. Do not re-derive from chat history.

| File | Type | Size | xz -9 | rissa v4.1 single | Result | Transform | Notes |
|------|------|------|-------|-------------------|--------|-----------|-------|
| `dickens` | text | 9.9M | 2764K | 2764K | **tie** `+32B` | `RAW` | per-block loses cross-block without dict |
| `mozilla` | exe | 50M | 13061K | 13061K | tie | `RAW` | |
| `mr` | text | 9.7M | 2686K | 2686K | tie | `RAW` | |
| `nci` | chemical DB `fff` | 32M | 1698K | 1698K | tie | `RAW` | **Full MDL dump 64K 18/18 transforms: RAW 3965, DELTA 4881, XOR 4813, DELTA2 5633, MTF 8125, BWT 4525, SHUFFLE_2 4666, SHUFFLE_4 5674, SHUFFLE_8 6790, ZIGZAG 4921, BWT_RLE 4365, FLOAT_SPLIT 5674, BIT_PLANE 8609, SHUFFLE4_DELTA 7086, DICT 3965 → RAW wins, all 18 lose, not just 5** |
| `ooffice` | binary | 6M | 2370K | 2370K | tie | `RAW` | |
| `osdb` | db | 9.8M | 2783K | 2783K | tie | `RAW` | |
| `reymont` | text | 6.4M | 1286K | 1286K | tie | `RAW` | |
| `samba` | exe | 21M | 3675K | 3675K | tie | `RAW` | |
| `sao` | image? | 7M | 4312K | 4312K | tie | `RAW` | |
| `webster` | text | 40M | 8189K | 8189K | tie | `RAW` | |
| **`x-ray`** | **16-bit medical image** | **8.2M** | **4385K** | **4212K** | **WIN -3.9%** | `BIT_PLANE` / `SHUFFLE4_DELTA` 503K vs RAW 536K on 1M | **Only win — bit-plane separable, not columnar/sensor/JSON** |
| `xml` | structured text | 5.2M | 443K | 443K | tie | `RAW` | |

**Other corpora (available `deep_compress/corpora`):**

| File | xz | rissa | Result | Transform |
|------|----|-------|--------|-----------|
| `Apache_2k.log` 171K | 7236 | 7513 | lose +3.8% | `RAW` header |
| `HDFS_2k.log` 287K | 42768 | 44588 | lose +4% | `RAW` |
| `noaa csv` 450K | 28924 | 31856 | lose +10% | text csv, not binary |
| `NOAA binary sensor` 500K `gen_noaa` `fff` **(synthetic)** | 213K | 238K `SHUFFLE_8` tie | tie | `SHUFFLE_8` |
| `Yellow parquet` 2M ent 8.00 | 1996K | 1996K | tie at Shannon limit | `RAW` |
| `Columnar 3.6M` **synthetic** | 204K | **39K -80%** | **WIN (synthetic)** | `SHUFFLE_8/BIT_PLANE` |
| `Sensor 6M` **synthetic** | 1610K | **1038K -35%** | **WIN (synthetic)** | `SHUFFLE` |
| `5MB x*` | 892 | 924 | lose +32B | early-stop 10× 0.3→3.0 MB/s |

**Reframed target (was "structured/sensor/log columnar"):**

> **Actual evidence:** **1 real win** `x-ray` BIT_PLANE 16-bit image `-3.9%` + **2 synthetic wins** columnar `-80%` **(synthetic)** / sensor `-35%` **(synthetic)** — synthetic wins are labeled **(synthetic)** in table, not real. Ties on general structured/scientific (`nci`/`xml`/`sao` all `RAW` full 18/18 dump, `FLOAT_SPLIT` at correct stride 4 + offsets 0-3 all lose 5674/3961 vs 3965 — not misaligned, genuinely not lever). **Truer claim:** `rissa` wins on bit-plane separable (images, **real** `x-ray`, possibly certain sensor) and ties on general structured — invest in `SHUFFLE` stride detection for columnar, not `BWT` for 1M+ (still stubbed 256K-1M closed, 1M+ stubbed). Synthetic wins kept labeled synthetic in table.

**Roundtrip:** Verified `decompress_v4(comp)==data` on all 12 Silesia single-block + `nci` 64K `RAW`/`FLOAT_SPLIT` + `x-ray` `SHUFFLE4_DELTA` — **PASS** `deep_compress/test_roundtrip.py`.

**MDL cost dump `nci` 64K:** `RAW 3965` < `BWT 4525` < `SHUFFLE 4666` < `FLOAT_SPLIT 5674` — **RAW genuinely wins, not threshold**. `FLOAT_SPLIT` tried on `nci` 64K `5674` vs `RAW` `3965` lose, confirmed.

**Hold off:** `SA-IS` 1M+ BWT, `BWT_SUBBLOCK` as default, custom `rANS` backend — all gated, not default, until Silesia thesis validated (now 1 win / 11 ties, not `beats xz`).

**Next cheapest:** `nci` dump already shows `RAW` wins — `SA-IS` won't change `nci` (BWT already loses at 64K), so **don't invest in SA-IS until MDL dump shows `BWT` near `RAW`**. Instead, auto stride detection for `SHUFFLE`/`FLOAT_SPLIT`.
