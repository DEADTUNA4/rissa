# Theory — rissa Hall of Fame

**Every idea in rissa named after the person who made it possible. `rissa` itself is Rissanen.**

---

## 1. Rissa Theory — The Whole Project

**Jorma Rissanen (MDL, 1978) + A.N. Kolmogorov (Complexity, 1965)**

```
Compressed = min_T [ Cost(T) + Cost(Model) + Cost(Data | Model) ]
```

The whole engine. Treat compression as *finding the shortest description*, not just squeezing bytes. Search 16 reversible `T` per block, keep the `T` with smallest total `Cost(T)+Cost(Model)+Cost(Data|Model)`. Uncomputable Kolmogorov made tractable by fixing the model set. No Free Lunch [Wolpert] — no transform wins on all inputs. See `deep_compress/THEORY.md:1` and `public/how-it-works.html`.

*Why Rissanen:* Without MDL, rissa is just 16 heuristics. With MDL, it is one equation.

---

## 2. RACD Theory — Record-Aligned Column Dictionary — GATED

**E.F. Codd (Relational Model, 1970) + Jim Gray (Columnar) — invented for rissa to fix CDC's failure on `nci` text**

**Problem:** CDC treats `nci` as undifferentiated bytes. Real `nci` is line/record-structured (`V2000`, `C 0 0 0`, `$$$$\n` SDF blocks, `~80` lines per record). Redundancy is field-level: column 2 ` 0  0 ` repeats 9,369×, not byte-level.

**Invention:** Detect record boundaries cheaply (`\n` split, `$$$$\n` for SDF), split each record into fields by whitespace (sniff first `N` lines), transpose: build **one dictionary per field/column position** — `Field 2` `6,145 → 244 4.0%` `96.0%` win.

**Measured:** `nci` 64K `1714` lines `16` field positions all `16/16` win `78.4-96.5%` reduction (`4.0%` remaining = `96%` win) with `reduction = 1 - comp/raw` rechecked — but this was **whitespace-normalized** `b' '.join` silently changing `b'  field1   field2'` → `b'field1 field2'`. Once fixed to `re.split(b'(\\s+)')` preserving `32` cols, `RACD` `95,160` vs `65,536` raw `+45%` `7421` vs `3965` lose. **RACD: tested and ruled out on real text data. Its apparent win was caused by whitespace bug; once fixed, loses to `RAW` on `nci`.** Whole `1M` sample `730,856` → `58,752` vs `RAW 68,852` was same bug — whole-file `33M` `23,383,582` transposed is `22.3M` intermediate not `33M` file, direct `lzma` `20.6%` not `compress_v4` MDL, no roundtrip. All three must pass.

**Status:** **Gated `--experimental` for future record-structured binary data, not promoted.** `RACD` `Codd/Gray` stays hall-of-fame but **ruled out on real text** — `nci` stays `RAW` tie. `23,383,582` was transposed intermediate, file is `33,553,445`; `18.7%` vs `20.6%` was `remaining` vs `reduction` mislabel, now `reduction = 1-comp/raw` consistently.

*Why Codd/Gray:* Columnar is Codd's relational + Gray's columnar — field, not byte.

---

## 3. Shannon Theory — Entropy Limit

**Claude Shannon (1948)**

```
H = -sum p log2 p   Shannon bytes = H/8 * len
```

Lower bound. `rissa` reports `bits/sym vs Shannon` `deep_compress/rans.py:12` not `10× closer` hype. Random 10M `ent 8.00` → `rissa` `10,487,002` tie at limit — correct fallback to `RAW`.

---

## 4. Huffman Theory — Order-0

**David A. Huffman (1952)**

`0 ≤ 1 bit/symbol` waste. `huffman.py:1` `build_tree` `512B` header `3%` at 16K → `0.4%` at 128K → `0.05%` at 1M. Replaced by `rANS` for fractional bits.

---

## 5. BWT Theory — Burrows-Wheeler

**Michael Burrows + David Wheeler (1994)**

Reorder `banana` → `nnbaaa` to group contexts. `transforms_v2.py:bwt_encode` radix 2-byte bucket up to 256K (was 4K naive `50K 2.3s`), `BWT_SUBBLOCK:16` `1M→4×256K` for 1M blocks. `Silesia` `x-ray` `BWT_MTF` not yet winning at 64K `4525` vs `RAW 3965`, so `SA-IS` 1M+ still stubbed `256K-1M closed, 1M+ stubbed`.

---

## 6. MTF Theory — Move-to-Front

**Bentley et al. (1986)**

After `BWT`, `MTF` turns local runs into many `0`s. `transforms_v2.py:mtf_encode` `bytearray` `pos` array, `MTF_RLE` uses 4-zero marker `[0,0,0,0,N-4]` to avoid `FE` ambiguity — fixed `RLE 2→4` `bwt_range.py:1`.

---

## 7. LZMA Theory — Lempel-Ziv-Markov

**Abraham Lempel + Jacob Ziv (1977/78) + Markov**

`xz -9` `64M` dict. `rissa` uses `lzma` backend after transforms + `preset_dict` killer `build_lzma_dict` `8-byte` freq + `CDC` `hash & 0xFFF` avg 4K, `64K` header `lzma.compress`ed `2.4K` (was `496K` raw miscalc) — `compressor_v4.py:12`.

---

## 8. rANS Theory — Asymmetric Numeral Systems

**Jarek Duda (2009)**

Range `prob 1..4095` `split = range*prob>>12` with `cache` carry. `bwt_range.py:1` `RangeEncoder`/`RangeDecoder` `prob += (bit*4096 - prob)>>5` adaptive, 4 contexts `last 2 bits`. Drafted, **gated `--experimental`** until Silesia thesis validated — not default.

---

## 9. Delta Theory — Predictive

**General (Gorilla/Prometheus for zigzag)**

`delta_encode: out[i]=in[i]-in[i-1]`, `DELTA_ZIGZAG` `((s<<1)^(s>>7))&0xFF` maps `-1 →1` (was `255`), `DELTA2`, `ORDER2` `2*prev - prev2`. `nci` `64K` `DELTA 4881` vs `RAW 3965` lose — correctly gated.

---

## 10. Shuffle Theory — Byte Transpose

**HDF5/Blosc + Jim Gray**

`SHUFFLE_4` `a0b0c0d0→aaaa bbbb` for 32-bit ints/floats where high bytes repeat. `stride` `2/4/8` cost `1B` counted in MDL. `FLOAT_SPLIT` 4-stream IEEE754, `BIT_TRANSPOSE` 8×8. `SHUFFLE4_DELTA` composition loud comment `Cost(T1)+Cost(T2)` at `transforms_v2.py:15`.

---

## 11. Dictionary Theory — Lempel-Ziv Dictionary

**Lempel-Ziv (1976) + Brotli/zstd**

`cdc_dict.py:1` `Rabin-Karp` `poly 0xBF window 64` `hash & 0xFFF==0` avg 4K chunks, top 4096 `FE FF+idx` `4B` token, `FE FE` escape — fuzzed `FE FE FE`, `FE FF FE`, start/end. `build_lzma_dict` vs `CDC` — `CDC` gated after file-scale `nci` `1,741,072` lose vs `xz`.

---

## 12. No Free Lunch

**David Wolpert (1996)**

No compressor beats all on all inputs. `rissa` wins on bit-plane separable `x-ray -3.9%` `BIT_PLANE`, synthetic columnar `-80%` **(synthetic)**, ties on general `11/12` Silesia `RAW` — reframed target: *wins on bit-plane separable, ties on general*.

---

**All theories together = rissa.** Each named after the person whose idea made that layer possible. Full stack `deep_compress/THEORY.md`, code `deep_compress/`, benchmarks `public/benchmarks.html` version-sorted `v4.4` latest first.
