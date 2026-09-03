# Developer — Every Variable, Internal Functions

**https://rissa.web.app/docs.html — `DOCUMENTATION.md` is the example place, this is the exhaustive reference.**

This is the exhaustive variable/function reference for hacking on `rissa`. For user guide see `GUIDE.md`, for format see `FORMAT.md`, for theory see `ARCHITECTURE.md`.

## Core — `compressor_v4.py`

- `BLOCK_1M = 1048576`, `BLOCK_4M = 4194304`, `DEFAULT_BLOCK = BLOCK_1M` — block sizes. `<=4M` file → single block `block_size = len(data)` to save header (5×1M 600B → single 32B).
- `MAGIC = b"RISA"`, `VERSION = 4`, `EXT = ".rissa"` — header. Legacy `DCM2` migrated.
- `build_lzma_dict(data, max_dict_size=65536, sample_size=1048576)` — CDC `hash & 0xFFF==0` avg 4K chunks → `Counter` top 4096 8-byte → `b"\x00".join` → `Max 64K`. Small `<8M` uses entire file, large uses 3×512K spread.
- `dict_bytes: bytes | None` — 64K dict, `zstandard.train_dictionary` or 6-gram fallback, MDL-gated `gain > overhead*0.5`.
- `zstd_dict: ZstdCompressionDict | None` — compiled for `ZstdCompressor(dict_data=...)`.
- `compress_v4(data, backend="lzma", level=9, block_size=DEFAULT_BLOCK, use_dict=True, use_two_pass=False, preset_dict_bytes=None, fast=False, force_dict=False, max_block=False)` — main. `fast` → `level=6` + `entropy_threshold=1.2`, `force_dict` prints `[rissa] forced`, `max_block` single for `<=15M`.
- `block: bytes` — slice `data[i:i+block_size]`
- `transformed: bytes`, `extra: bytes` — `enc(block)` returns both, `extra` 0-2B counted `total = len(comp)+1+len(extra)`
- `priority_order = [0,5,16,1,7,...]` — RAW, BWT_MTF, BWT_SUBBLOCK, DELTA, SHUFFLE... BWT caps 256K, SUBBLOCK for 1M.
- `shannon(d) -> float` — `-sum(p log2 p)` `Counter`, `ent_bytes = ent/8*len`
- `entropy_threshold = 1.2 if fast else 1.1` — early stop `total <= ent*thr` + hard `<1%` raw `total < len(block)*0.01` → 5MB `x*` 0.3→3.0 MB/s 10×.
- `best_tid: int`, `best_extra`, `best_payload`, `best_name: str` — MDL winner, `TID 99 XOR_PREV` `100 BIT_PLANE` special.
- `xor_prev_block_encode(data, prev_block)` — `out[i]=data[i] ^ prev_block[i%len(prev_block)]`, disabled when `use_mp` (6 workers) to avoid silent wrong decode — loud check `if use_mp: pass` before `99`.
- `bit_plane_separation_encode` — `len%4==0` → `4 streams` `byte 0..3` of each `I`, high bytes first.
- `use_mp = len(blocks)>4 and block_size>=BLOCK_1M` — 6 RAM / 2-3 HDD, `shared_memory` stub.
- `chosen: Counter[str]` — histogram `{'RAW':1, 'SHUFFLE_8':4}`

Example:

```python
from deep_compress.compressor_v4 import compress_v4, decompress_v4
comp, hist, d = compress_v4(open("telemetry.bin","rb").read(), backend="lzma", block_size=1048576, use_dict=True, fast=True)
print(hist)  # Counter({'SHUFFLE_8': 4})
assert decompress_v4(comp) == data
```

## Transforms — `transforms_v2.py` (16)

- `data: bytes`, `out: bytearray`, `stride: int` 2/4/8, `primary: int` `>H`, `zz: int` zigzag `((s<<1)^(s>>7))&0xFF` (e.g., -1 →1), `transposed: list[int]` 8×8. All `encode(data) -> (bytes, extra)` `decode(bytes, extra) -> bytes` reversible, size-preserving except `SHUFFLE` (same).

Fixed errors: `RLE 2→4 zero marker [0,0,0,0,N-4]` for `0xFE` literal `FE FE` escape, zigzag double decode, `bwt_encode` radix 2-byte bucket up to 256K, `BWT_SUBBLOCK` 1M→4×256K.

Example:

```python
from deep_compress.transforms_v2 import delta_encode, shuffle_encode
delta_encode(b"\x10\x11\x13")  # b"\x10\x01\x02"
shuffle_encode(b"abcd"*4, 4)   # b"aaaa bbbb cccc dddd"
```

## Entropy — `huffman.py` / `rans.py` / `bwt_range.py`

- `freq: list[int]` 256, `codes: dict[int,str]`, `padding: int 0..7`, `encoded: bytes`, `entropy: float`, `bits_per_sym: float` `-sum(p log2 p)` `rans.py:12`.
- `huffman_order1_encode_block(data)` — `256` contexts `ctx_freq[prev][cur]`, `256` trees — gated behind `--experimental`, not default until Silesia validated. Replaces `order-1 Huffman` 5-10% over `order-0` on `BWT` output.

Example: `b"a"*1000` ent 0.00 Huffman 1.00 b/sym → rANS ~0.

## CDC — `cdc_dict.py`

- `rabin_karp_cdc(data, window=64, mask=0xFFF)` → `chunks` avg 4K, `poly 0xBF`
- `build_cdc_dict(data, max_entries=4096)` → `top` 4096 chunks
- `cdc_substitute_encode(data, cdc_dict)` → `FE FF + idx` token `4B` (was `FE + idx` 3B ambiguous), literal `FE → FE FE` — fuzzed `FE FE FE`, `FE FF FE`, start/end.

## CLI / GUI — `deep_compress/rissa.py` / `tools/rissa_tool.py`

- `args.input/output/block/dict`, `var_in: StringVar` — `rissa input.bin -o out.rissa --block 131072 --dict`

Fixed: `rissa` import `ModuleNotFoundError` via `try: from transforms_v2 except: from .transforms_v2`.

Full variable list with examples is also in `DOCUMENTATION.md` (example place) — this file is the exhaustive companion.
