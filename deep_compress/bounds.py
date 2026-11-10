"""Runtime decode guards (added in 4.6.6 - see FORMAT.md "Runtime guards").

These are DECODER-side sanity caps only. They do not change the .rissa on-disk
format, and no valid stream can hit them:

- valid v2 blocks are <= 65535B (ORIG_LEN is 16-bit there),
- valid v3 blocks are <= 4GB in theory but writers emit 16K/64K/128K,
- valid v4 blocks are <= 4MB (adaptive single-block files are <= 4MB, and
  max_block is capped at 15MB),
- per-TID transformed lengths are bounded by construction (IDENTITY family is
  exactly orig_len; RLE encodes at 3B/1B worst case; BWT_MTF_RLE's last stage
  rle_zero_encode expands runs of exactly 4 to 5B/4B = 1.25x).

An attacker-controlled container (the compressed byte stream is the attack
surface) can declare huge ORIG_LEN / COMP dynamics that used to be trusted
BEFORE decoding. Decompression bombs (a small zlib/lzma/zstd payload that
expands to gigabytes) were previously decoded in full and only afterwards
rejected by the ORIG_LEN cross-check. Now the backend decode is bounded to
what a stream written by THIS project could possibly need for that block:
allocation is capped at bound+1 bytes and anything larger is rejected with
:class:`OutputLimitError` before the big output exists.

Backend library errors (zlib.error etc.) still propagate unwrapped, per the
error contract in errors.py. Only the size guard raises rissa's own error.
"""
from __future__ import annotations
import os
__all__ = [
    "OutputLimitError",
    "DEFAULT_MAX_BLOCK_OUTPUT",
    "MAX_DICT_BYTES",
    "block_bound",
    "check_orig_len",
    "check_total",
    "decode_backend_block",
]

try:
    from .errors import FormatError, OutputLimitError
except ImportError:
    from errors import FormatError, OutputLimitError


# Block claims bigger than this cannot come from a valid .rissa stream
# (largest legal writer output: v4 max_block 15MB). Default 1GB is a 64x
# margin. Override with RISSA_MAX_BLOCK_OUTPUT (bytes); "0" disables the
# absolute cap (expansion-ratio caps stay on).
DEFAULT_MAX_BLOCK_OUTPUT = 1 << 30

# The whole v4 dict is dict_to_use = preset_dict_bytes[:32768], so a valid
# stream never stores a decoded dict longer than 32768B. 1MB here is a 32x
# margin. The decoded dict length is also cross-checked against the stored
# DICT_LEN field (that field was read but never validated before 4.6.6).
MAX_DICT_BYTES = 1 << 20


def _absolute_cap() -> int | None:
    """RISSA_MAX_BLOCK_OUTPUT override, parsed lazily (None = guard off)."""
    raw = os.environ.get("RISSA_MAX_BLOCK_OUTPUT", "")
    if raw == "":
        return DEFAULT_MAX_BLOCK_OUTPUT
    try:
        val = int(raw, 0)
    except ValueError:
        return DEFAULT_MAX_BLOCK_OUTPUT
    return val if val > 0 else None


# Worst-case |transformed| / orig_len for every TID that can appear in a
# stream. Anything outside this table is rejected at container level already.
_EXPANSION = {
    0: 1, 1: 1, 2: 1, 3: 1, 4: 1, 5: 1,          # RAW/DELTA/XOR/DELTA2/MTF/BWT_MTF
    6: 1, 7: 1, 8: 1,                              # SHUFFLE_2/4/8 (same length)
    9: 1, 10: 1, 11: 1,                            # ZIGZAG/DELTA2_ZIGZAG/ORDER2
    12: 2,                                         # BWT_MTF_RLE (rle_zero 1.25x, margin)
    13: 1, 14: 1, 15: 1, 16: 1, 17: 1,             # FLOAT_SPLIT/BIT/SHUFFLE4_DELTA/BWT_SUBBLOCK/DICT
    19: 3,                                         # RLE: worst 65535-run split = 3B/1B
    99: 1, 100: 1,                                 # XOR_PREV / BIT_PLANE (v4)
}
_SLACK = 64  # bytes of headroom above the exact ratio bound


def block_bound(orig_len: int, tid: int | None = None) -> int | None:
    """Upper bound on the post-backend (transformed) byte count of one block.

    Combination of the absolute per-block cap and the per-TID expansion
    ratio. Returns None when the absolute cap is disabled by env override.
    """
    absolute = _absolute_cap()
    ratio_cap = orig_len * _EXPANSION.get(tid, 1) + _SLACK if tid is not None else None
    if ratio_cap is not None and ratio_cap < absolute:
        return ratio_cap if absolute is not None else ratio_cap
    return absolute


def check_orig_len(orig_len: int, tid: int | None, what: str) -> int | None:
    """Reject ORIG_LEN values no valid writer could produce (before any alloc)."""
    absolute = _absolute_cap()
    if absolute is not None and orig_len > absolute:
        raise FormatError(f"{what}: ORIG_LEN {orig_len}B exceeds the per-block guard "
                          f"{absolute}B (RISSA_MAX_BLOCK_OUTPUT overrides; no valid "
                          f"rissa stream contains such a block)")
    return block_bound(orig_len, tid)


def check_total(done: int, max_output_size: int | None, what: str) -> None:
    """Stream-level output ceiling (opt-in via max_output_size param)."""
    if max_output_size is not None and done > max_output_size:
        raise OutputLimitError(f"{what}: decoded {done}B exceeds max_output_size {max_output_size}B")


def decode_backend_block(comp: bytes, backend: str, bound: int | None, has_zstd: bool = True, zstd_dict=None, lzma_preset_dict=None) -> bytes:
    """One backend decompression bounded to ``bound`` bytes of output.

    Peak memory is at most bound+1 bytes regardless of what the payload
    expands to; growth past bound raises OutputLimitError. For bound=None
    (absolute guard disabled) one-shot unbounded decode is used - byte and
    exception identical to the pre-4.6.6 code paths.
    """
    import zlib
    import lzma
    if backend == "zlib":
        if bound is None:
            return zlib.decompress(comp)
        do = zlib.decompressobj()
        out = do.decompress(comp, bound + 1)
        if len(out) > bound:
            raise OutputLimitError(f"backend would decode past the block guard ({bound}B)")
        # parity with one-shot zlib.decompress: it raises zlib.error on a
        # truncated stream; decompressobj would return the partial prefix.
        if not do.eof:
            raise zlib.error("Error -5 while decompressing data: incomplete or truncated stream")
        return out
    if backend == "lzma":
        if bound is None:
            if lzma_preset_dict:
                try:
                    return lzma.decompress(comp, preset_dict=lzma_preset_dict)
                except TypeError:
                    return lzma.decompress(comp)
            return lzma.decompress(comp)
        # parity with one-shot lzma.decompress: it decodes a single LZMA
        # member, accepts (and loops) concatenated members, ignores trailing
        # bytes after a valid member, raises LZMAError when a member ends
        # without the end-of-stream marker. Loop with per-member bound.
        parts = []
        acc = 0
        data = comp
        usable_frame = True
        while True:
            quota = bound + 1 - acc  # >= 1: acc exceeded bound raises first
            d = lzma.LZMADecompressor()
            try:
                chunk = d.decompress(data, max_length=quota)
            except lzma.LZMAError:
                if not usable_frame:
                    break  # trailing bytes after a valid member: ignored (parity)
                raise
            acc += len(chunk)
            if acc > bound:
                raise OutputLimitError(f"backend would decode past the block guard ({bound}B)")
            parts.append(chunk)
            if d.eof:
                data = d.unused_data
                if not data:
                    return b"".join(parts)
                usable_frame = False
                continue
            if len(chunk) < quota:
                # input exhausted without the end-of-stream marker
                raise lzma.LZMAError("Compressed data ended before the end-of-stream marker was reached")
            # quota hit mid-member: more output pending, drain (acc == bound+1
            # can only raise above, so a full drain never actually loops)
            data = b""
            usable_frame = False
    if backend == "zstd":
        if not has_zstd:
            # mirrors the historical no-zstd fallback path
            if bound is None:
                return zlib.decompress(comp)
            return decode_backend_block(comp, "zlib", bound)
        import zstandard as zstd
        dctx = zstd.ZstdDecompressor(dict_data=zstd_dict) if zstd_dict else zstd.ZstdDecompressor()
        if bound is None:
            return dctx.decompress(comp)
        # stream_reader instead of one-shot decompress: one-shot allocates the
        # frame-header-declared content size up front (a header-only vector)
        # and, on this python-zstandard, ignores max_output_size. stream_reader
        # decodes incrementally, so nothing larger than bound+1 ever materializes.
        reader = dctx.stream_reader(comp)
        try:
            out = reader.read(bound + 1)
        finally:
            reader.close()
        if len(out) > bound:
            raise OutputLimitError(f"backend would decode past the block guard ({bound}B)")
        return out
    raise FormatError(f"unknown backend {backend!r} for bounded decode")


def decode_dict_bounded(dict_compressed: bytes, dict_orig_len: int, what: str) -> bytes:
    """v4 header dict: bounded lzma decode + cross-check against DICT_LEN."""
    if dict_orig_len > MAX_DICT_BYTES:
        raise FormatError(f"{what}: DICT_LEN {dict_orig_len}B exceeds the dict guard "
                          f"{MAX_DICT_BYTES}B (valid writers store at most 32768B)")
    import lzma
    d = lzma.LZMADecompressor()
    try:
        dict_bytes = d.decompress(dict_compressed, max_length=MAX_DICT_BYTES + 1)
    except Exception as e:
        raise FormatError(f"{what}: dict lzma decode failed: {type(e).__name__}: {e}") from e
    if len(dict_bytes) != dict_orig_len:
        raise FormatError(f"{what}: decoded dict {len(dict_bytes)}B != DICT_LEN {dict_orig_len}B "
                          f"declared in header")
    return dict_bytes
