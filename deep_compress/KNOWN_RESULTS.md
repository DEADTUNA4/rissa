# Known Results — rissa Single Source of Truth

**Updated: 2026-09-03 — v4.1 — Silesia single-block `<=4M` adaptive, 12 files `deep_compress/silesia/`**

This is the standing table — win/tie/loss per file type, updated as we go. Do not re-derive from chat history.

| File | Type | Size | xz -9 | rissa v4.1 single | Result | Transform | Notes |
|------|------|------|-------|-------------------|--------|-----------|-------|
| `dickens` | text | 9.9M | 2764K | 2764K | **tie** `+32B` | `RAW` | per-block loses cross-block without dict |
| `mozilla` | exe | 50M | 13061K | 13061K | tie | `RAW` | |
| `mr` | text | 9.7M | 2686K | 2686K | tie | `RAW` | |
| `nci` | chemical DB `SDF` `V2000` | 32M | 1698K | **1380K** | **WIN -18.7%** | `RACD` `23,383,582` transposed `→ 1,380,592` `20.6%` win vs `xz` `1,738,884` (single 64K `RAW` 3965 wins all 18, but file-scale `RACD` whole `33M` wins) |
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

> **Actual evidence:** **2 real wins** `x-ray` `BIT_PLANE -3.9%` + **`nci` `RACD -18.7%` file-scale `33M`** + **2 synthetic wins** columnar `-80%` **(synthetic)** / sensor `-35%` **(synthetic)** — `nci` now `RACD` win `20.6%` on full `33M` `23M` transposed `→ 1,380,592` vs `xz 1,738,884`, `SDF` `V2000` `80` lines/record drift handled per-block `0-7` sweep `4,2,4` + `>H`/`>I` length-prefix `45,694` correct. `nci` 64K `RAW` still wins all 18/18 (`FLOAT_SPLIT` `+1700` correctly loses on text `SDF`, not misaligned). **Truer claim:** `rissa` wins on **record-aligned columnar** (`nci` `RACD` + `x-ray` `BIT_PLANE`) and ties on general text — `RACD` is official, not gated.

**Roundtrip:** Verified `decompress_v4(comp)==data` on all 12 Silesia single-block + `nci` 64K `RAW`/`FLOAT_SPLIT` + `x-ray` `SHUFFLE4_DELTA` — **PASS** `deep_compress/test_roundtrip.py`.

**MDL cost dump `nci` 64K:** `RAW 3965` < `BWT 4525` < `SHUFFLE 4666` < `FLOAT_SPLIT 5674` — **RAW genuinely wins, not threshold**. `FLOAT_SPLIT` tried on `nci` 64K `5674` vs `RAW` `3965` lose, confirmed.

**Hold off:** `SA-IS` 1M+ BWT, `BWT_SUBBLOCK` as default, custom `rANS` backend — all gated, not default, until Silesia thesis validated (now 1 win / 11 ties, not `beats xz`).

**Next cheapest:** `nci` dump already shows `RAW` wins — `SA-IS` won't change `nci` (BWT already loses at 64K), so **don't invest in SA-IS until MDL dump shows `BWT` near `RAW`**. Instead, auto stride detection for `SHUFFLE`/`FLOAT_SPLIT`.
