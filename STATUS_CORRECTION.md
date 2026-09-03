# Status Correction — Precise, not 5 closed

**Previous claim "5 closed" overstates. Accurate: 3 closed, 1 capped, 1 still pending.**

- **3 closed:** CDC escaping `cdc_dict.py:1` (verified `FE FE`, `FE FF FE`, `FE` at start/end, multi-FE), range coder renormalization `bwt_range.py:1` drafted but gated (not default), canary `5MB x*` 2.3x → single-block 924 vs 892 +32B (adaptive `<=4M` single).
- **1 capped (not closed):** BWT radix 2-byte up to 256K closed, sub-block `BWT_SUBBLOCK:16` `4×256K` handles 256K-1M, **1M+ still stubbed** — needs SA-IS 200-300 lines `array('I')`. 1M is now default block size, so stub is live, not future TODO. Reframe as "256K-1M closed, 1M+ stubbed".
- **1 still pending and now further delayed:** Silesia `nci`/`xml` core thesis test — proxy showed `RAW` tie +32B (no transform triggered, not informative). Real test needs `silesia.zip:68M` `silesia/:212M` [Deorowicz] which was deleted for "clean" (`E:\Documents\Rombil\deep_compress\silesia` removed, now `deep_compress/download_corpora.py` must re-download 68M on slow HDD). Self-inflicted delay on most important open question — "clean" was not worth losing it. Worth reconsidering: keep `silesia/` gitignored but not deleted, or keep 1 file `nci`/`xml` for quick thesis test.

**CDC edge:** Verified `0xFE 0xFE 0xFE` (3 FE), `0xFE 0xFF 0xFE` (token boundary), `FE` at start/end — all pass with `FE FE` escape and `FE FF + idx` token.

**xor_prev_block vs streaming:** Now loud: `compressor_v4.py:12` skips `TID 99 XOR_PREV` when `use_mp` (6 workers) to avoid silent wrong decode; proper fix is `ValueError` if both requested or carry `prev_block_raw` in streaming state. Don't leave as silent footgun.

**Composition cost:** `SHUFFLE4_DELTA:15` hardcoded as single TID with single extra `b"\x04"` — general `T1->T2` MDL is `Cost(T1)+Cost(T2)+Cost(Data|T1,T2)` not `1+len(extra)`. Left loud comment at `transforms_v2.py:15` and `compressor_v4.py:12` explaining what would need to change for second pair.

Net: 3 closed, 1 capped, 1 pending and delayed — precision matters for skimmed docs.
