# rissa Documentation — Every Variable, How It Works, With Examples

**https://rissa.web.app — Apache 2.0 — `pip install rissa-compress`**

This document lists every key variable in `rissa` and explains with examples. No em dashes. Fixed errors noted.

## Core Equation

```
Compressed = min_T [ Cost(T) + Cost(Model) + Cost(Data | Model) ]
```

Pick transform `T` with smallest total description length per block.

---

## 1. `transforms_v2.py` — 16 Transforms

### `data: bytes` — input block
Type: `bytes`, 0 to `BLOCK_SIZE` (64K/128K). Example: `b"hello"` or `bytes([1,2,3,4])`.

### `out: bytearray` — transformed output
Mutable buffer, same length as `data` for most transforms. Example: `delta_encode(b"\x01\x02\x03")` -> `bytearray([1,1,1])`.

### `stride: int` — shuffle width
For `shuffle_encode(data, stride)`. Values 2,4,8. Example: `stride=4` groups 4-byte records: `b"a0b0c0d0 a1b1c1d1"` -> `b"aa bb cc dd"`. Extra `b"\x04"` stored, counted in MDL.

### `primary: int` — BWT primary index
0 to `len(data)-1`, stored as `>H` 2 bytes. Example: `bwt_encode(b"banana")` -> `(b"nnbaaa", 3)`.

### `zz: int` — zigzag value
Maps signed -128..127 to 0..255. Example: `delta 1 -> zz 2`, `delta -1 (255) -> zz 1`. `zigzag_encode([100,99])` -> delta -1 -> zz 1.

### `transposed: list[int]` — 8x8 bit matrix
For `bit_transpose_encode`. Example: 8 bytes `0b00000001` each -> transposed `0b11111111` etc.

**Fixed errors:**
- RLE zero marker: was `[0,0,N]` ambiguous on `[0,0,5]` literal → fixed to 4-zero marker `[0,0,0,0,N-4]` `transforms_v2.py:15`.
- Zigzag decode: duplicated logic with wrong `&0xFF` → fixed to `signed = (zz>>1) ^ -(zz&1)` then `&0xFF` `transforms_v2.py:9`.

Example for each transform:

```python
from deep_compress.transforms_v2 import delta_encode, shuffle_encode, bit_transpose_encode
delta_encode(b"\x10\x11\x13")  # b"\x10\x01\x02"
shuffle_encode(b"abcd"*4, 4)   # b"aaaa bbbb cccc dddd"
bit_transpose_encode(b"\x01\x02"*4)  # 8x8 transpose
```

---

## 2. `compressor_v3.py` — Per-block MDL

### `BLOCK_SIZE_64K = 65536`, `BLOCK_SIZE_128K = 131072`
Block size. 128K has 0.4% header vs 3% at 16K. Example: 500K file → 8 blocks at 64K, 4 at 128K.

### `MAGIC = b"RISA"` , `VERSION = 3`, `EXT = ".rissa"`
Header 4 bytes. Legacy `DCM2` auto-migrated. Example file starts `52 49 53 41 03`.

### `dict_bytes: bytes | None` — shared dictionary
1MB sample → 64KB via `zstandard.train_dictionary` fallback 6-grams. MDL-gated: only kept if `with+dict < without` `compressor_v3.py:12`. Example: 46MB parquet truncated → dict disabled (overhead), 2MB text → dict 65K.

### `zstd_dict: ZstdCompressionDict | None`
Compiled dict for `ZstdCompressor(dict_data=...)`. Example: `zstd.ZstdCompressor(level=19, dict_data=zstd_dict).compress(block)`.

### `block: bytes` — one chunk
Slice `data[i:i+block_size]`. Example: `data[0:65536]`.

### `transformed: bytes`, `extra: bytes`
`enc(block)` returns both. `extra` is 0-2B (BWT primary, stride). Counted in `total = len(comp)+1+len(extra)` `compressor_v3.py:35`.

### `best_tid: int`, `best_extra: bytes`, `best_payload: bytes`, `best_name: str`
MDL winner per block. Example: `best_tid=7` `SHUFFLE_4` `best_extra=b"\x04"`.

### `hist: Counter[str]`
Histogram of chosen transforms. Example: `Counter({'RAW':8, 'SHUFFLE_8':2})`.

### Streaming `compress_stream(in_stream, out_stream, ...)`
For `for block in stream` without RAM. Example: `compress_stream(open('in.bin','rb'), open('out.rissa','wb'), block_size=131072)`.

---

## 3. `huffman.py` / `rans.py` — Entropy

### `freq: list[int]` — 256 counts
`freq[65]` for `A`. Example: `b"AAA"` → `freq[65]=3`.

### `codes: dict[int, str]` — Huffman codes
`65: "0"` frequent. Example: `build_codes(tree)`.

### `padding: int` — 0..7
Bits to fill last byte. Example: bit string `101` → `10100000` padding 5.

### `encoded: bytes`
Packed bits. Example: `huffman_encode_block(b"AAA")` → `b"\x00"`.

### `entropy: float`, `bits_per_sym: float`
Shannon ` -sum(p log2 p)` `rans.py:12`. Example: `b"a"*1000` ent 0.00, Huffman 1.00 b/sym → rANS would be ~0 (shows Huffman waste).

---

## 4. `rissa` package — `rissa/__init__.py`

### `level: int` — 1..4 maps to zstd 3,6,19,22
Example: `rissa.compress(data, level=3)` → `level 19`.

### `backend: str` — "zstd" | "lzma" | "zlib" | "huffman"
Example: `compress_with_dict(data, backend="zstd")`.

---

## 5. CLI `deep_compress/rissa.py` / `tools/rissa_tool.py`

### `args.input`, `args.output`, `args.block`, `args.dict`
CLI vars. Example: `rissa input.bin -o out.rissa --block 131072 --dict`.

### `var_in: StringVar`, `var_out: StringVar` — GUI
Tkinter file paths. Example: `var_in.get()` → `"C:/data.bin"`.

---

## Fixed Errors Summary

1. RLE marker 2→4 zeros `transforms_v2.py:15`
2. Zigzag double decode `transforms_v2.py:9`
3. `__pycache__` clean, `silesia.zip` 68MB removed, `corpora/*.parquet` ignored `.gitignore:1`
4. Em dashes → hyphens (14 files)
5. `rissa` import `ModuleNotFoundError` fixed via `try: from transforms_v2 except: from .transforms_v2`

## Quick Example End-to-End

```python
import rissa
from deep_compress.compressor_v3 import compress_with_dict, decompress_with_dict

data = open("telemetry.bin","rb").read()  # 16-byte structs: <I fff>
comp, hist, d = compress_with_dict(data, backend="zstd", block_size=131072, use_dict=True)
print(len(data), "->", len(comp), hist)  # 500000 -> 238000 Counter({'SHUFFLE_8':4})
assert decompress_with_dict(comp) == data

# Simple API
c = rissa.compress(data, level=3)  # level 3 = zstd 19
assert rissa.decompress(c) == data
```
