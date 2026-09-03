# rissa - Architecture Decisions (review response)

**rissa - Jorma Rissanen MDL 1978 - https://rissa.web.app - `rissa input -o output.rissa` (MAGIC `RISA` v3)**

## Transform Layer - Done
- Added `DELTA_ZIGZAG` `transforms_v2.py:9` (signed delta -> zigzag, for Gorilla-style negative small deltas)
- Added `DELTA2_ZIGZAG` `transforms_v2.py:12` (second-order with zigzag for timestamps)
- Added `ORDER2` `transforms_v2.py:13` (predict 2*x[n-1]-x[n-2], for text)
- Fixed `RLE_ZERO` `transforms_v2.py:15` to 4-zero marker `[0,0,0,0, N-4]` unambiguous, used only inside `BWT_MTF_RLE` `transforms_v2.py:105` (bzip2 pipeline BWT->MTF->RLE)
- Added `FLOAT_SPLIT` `transforms_v2.py:58` (IEEE754 4-stream, separates sign/exponent/mantissa)
- `SHUFFLE_2/4/8` already handles byte-shuffle/columnar transpose with stride cost (1 byte extra) counted in MDL `compressor_v2.py:35`
- Bit-transpose flagged as v3 (fixed-width columnar, needs stride detection, heavy)
- XOR-with-prev-block flagged as v3 (needs inter-block state, streaming unfriendly)
- Transform composition `T1->T2` flagged as v3 (e.g., SHUFFLE+DELTA). Current is single-T per block; stacking is next design fork.

Cost model: every `extra` (stride, primary) is `len(extra)` added to `total = len(comp)+1+len(extra)` `compressor_v2.py:35`. Verified per-block, not per-file.

## Grammar Layer - Decision
**Fork: per-block vs global**

- **Per-block Re-Pair at 4-16KB**: tested, not worth complexity. At this granularity plain LZ77 window outperforms Re-Pair for less code, and Re-Pair's priority queue + cycle detection is fragile (silent corruption on `aaaa`, `""`, 1MB same-byte if not adversarial-tested).
- **Global**: loses block-parallelism/streaming, but real grammar power.
- **Chosen middle for v2**: **Shared dictionary** (brotli static / zstd trained dict style). One global pass samples first 1MB or trains on all blocks to build dictionary, then per-block transform selection on top of dictionary-substituted data. Keeps streaming (dictionary is header) and block-parallelism. `grammar.py:12` stays disabled in `compressor_v2.py` until adversarial harness passes.

Implementation sketch for v3:
1. Sample 10% of blocks, build Re-Pair dictionary (max 64KB)
2. Store dictionary in file header (versioned)
3. Per-block: first apply dictionary substitution, then MDL transform search.

## Entropy Coder - Path
- Current: static per-block order-0 Huffman `huffman.py:1` with 512-byte freq table `compressor_v2.py:35` = 3-12% overhead at 16KB. Next: delta-compress freq table via RLE+ANS (sooner than rANS).
- Upgrade: **rANS** [Duda] well-documented, pairs with block structure, replaces Huffman. Not "10x closer" - will report `bits/symbol vs Shannon entropy` per file.
- Order-1 context `p(byte|prev)` before rANS is the big achievable win (closes PPM gap without neural). Planned as `context_huffman.py`.

## Predictor Ensemble - Scoped
- Honest speed budget: PAQ/CMIX 100-1000x slower than zstd. Will be **pluggable `--ultra` mode**, not default (like zstd --ultra, xz extreme).
- First: logistic mixing of 2-3 simple predictors (order-1, order-2, match model) as in PAQ, testable in isolation, no training infra.
- Neural (byte-level MLP) only after ablation on own data; 10k-param "10-20%" figure not cited until measured.

## Format Versioning
Already: `MAGIC b"DCM2"` `compressor_v2.py:7` + `VERSION=2` + `backend_id` per file. Allows evolution without breaking old files. Determinism: transform selection is deterministic (sorted `TRANSFORMS_V2` iteration, no hash tie-break); if hash used later, will seed.

## Streaming
Current `compressor_v2.py:42` is whole-file-in-memory block loop. Real-world needs streaming: decision is to keep block-independent (no cross-block state except optional global dict in header) so streaming is `for block in stream: compress_block(block)`. Flagged for v3 if global dict requires 2-pass.
