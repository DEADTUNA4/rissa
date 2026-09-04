# Guide — How to use rissa

**https://rissa.web.app — v4.4 — `pip install rissa-compress`**

## How to use

### Python API

```python
import rissa

# Simple
data = open("telemetry.bin", "rb").read()
compressed = rissa.compress(data, level=3)  # 1:3 2:6 3:19 4:22 -> zstd 3,6,19,22
assert rissa.decompress(compressed) == data

# Advanced per-block control
from deep_compress.compressor_v3 import compress_with_dict, decompress_with_dict
comp, hist, dict_bytes = compress_with_dict(
    data, backend="zstd",  # or "lzma", "zlib", "huffman"
    block_size=131072,     # 64K, 128K, 1M, 4M, or len(data) for single
    use_dict=True,         # 1MB sample -> 64KB shared dict, MDL-gated
    level=19
)
print(hist)  # Counter({'SHUFFLE_8': 4, 'RAW': 1})
assert decompress_with_dict(comp) == data

# v4 with dict and two-pass
from deep_compress.compressor_v4 import compress_v4, decompress_v4
comp, hist, d = compress_v4(data, backend="lzma", block_size=1048576, use_dict=True, use_two_pass=True, fast=False)
assert decompress_v4(comp) == data
# force dict for debugging
comp, hist, d = compress_v4(data, backend="lzma", force_dict=True, max_block=True)
```

### CLI

```bash
rissa input.bin -o output.rissa                  # default 64K, zstd
rissa input.bin -o output.rissa --block 131072   # 128K
rissa input.bin -o output.rissa --block 1048576 --dict  # 1M + shared dict
rissa input.bin -o output.rissa --block 4194304 --dict  # 4M max
rissa -d output.rissa -o restored.bin
rissa --help

# Direct module
python -m deep_compress.rissa input.bin -o out.rissa --block 65536
python tools/rissa_tool.py gui                   # Tkinter GUI

# Streaming (no RAM limit)
python -c "from deep_compress.compressor_v3 import compress_stream, decompress_stream; compress_stream(open('in.bin','rb'), open('out.rissa','wb'), block_size=131072)"
```

## Choosing block sizes

| File size | Recommended | Why |
|-----------|-------------|-----|
| <= 4MB | `block_size = len(data)` (single block, auto in v4) | Header 32B vs 600B (5×1M), 0.05% at 1M |
| 4-50MB | `1M` (default) | Balances 12-thread pool (100MB → 100 tasks) |
| >50MB arch | `4M` + `use_two_pass=True` | Larger window (64M dict) helps, sub-block BWT still 256K |
| Small <1KB | any | Header dominates, rissa falls back to RAW |

`header 512B at 16K =3% → 0.4% at 128K → 0.05% at 1M` — v4 adaptive does `<=4M → single` automatically.

## Streaming

```python
from deep_compress.compressor_v3 import compress_stream, decompress_stream
with open('big.bin','rb') as fin, open('big.rissa','wb') as fout:
    compress_stream(fin, fout, block_size=131072, use_dict=False)
with open('big.rissa','rb') as fin, open('big.out','wb') as fout:
    decompress_stream(fin, fout)
```

`for block in stream` without whole-file RAM. `xor_prev_block` disabled in parallel/streaming (loud check in `compressor_v4.py`) — use sequential for that transform.

## Python API details

- `rissa.compress(data, level=3, block_size=65536, backend="zstd", use_dict=False)` → `bytes` with `MAGIC RISA`
- `rissa.decompress(data)` → `bytes`, auto-migrates `DCM2` legacy
- `compress_with_dict` returns `(bytes, Counter, dict_bytes)` for inspection
- Deterministic: sorted `TRANSFORMS_V2` iteration, same input → same `.rissa`

## CLI details

- `--block` 4096,16384,65536,131072,1048576,4194304
- `--dict` enables 1MB→64KB `zstandard.train_dictionary` fallback 6-grams, MDL-gated (`with+dict < without`)
- `--backend` `zstd` (default) `lzma` `zlib` `huffman`
- `--level` maps 1→3,2→6,3→19,4→22
- `--stream` for `compress_stream`

Examples in `deep_compress/test_roundtrip.py` and `public/docs.html`.
