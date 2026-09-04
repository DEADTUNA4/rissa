"""
Main Compressor: Adaptive Transform Search + Huffman
Implements MDL theory: Size = Size(transform) + Size(data|model)
v1: Simple reliable version (transform search + Huffman). Grammar/ANS are layer 2/3 upgrades.
"""
import struct
try:
    from huffman import huffman_encode_block, huffman_decode_block
except ImportError:
    from .huffman import huffman_encode_block, huffman_decode_block
try:
    from transforms import TRANSFORMS
except ImportError:
    from .transforms import TRANSFORMS

BLOCK_SIZE = 4096
MAGIC = b"RISA"  # rissa v1
VERSION = 1

def compress(data: bytes) -> bytes:
    out = bytearray()
    out.extend(MAGIC)
    out.append(VERSION)
    if len(data)==0:
        blocks=[b""]
    else:
        blocks = [data[i:i+BLOCK_SIZE] for i in range(0, len(data), BLOCK_SIZE)]
    out.extend(struct.pack(">I", len(blocks)))
    for block in blocks:
        best_tid = 0
        best_extra = b""
        best_encoded = None
        best_freq = None
        best_padding = 0
        best_size = float('inf')
        for tid, (name, enc_fn, dec_fn) in TRANSFORMS.items():
            if tid==3 and len(block)>2048:  # BWT limit
                continue
            try:
                transformed, extra = enc_fn(block)
            except Exception:
                continue
            if transformed is None:
                continue
            encoded, freq, padding, _ = huffman_encode_block(transformed)
            size = len(encoded) + len(extra)
            if size < best_size:
                best_size = size
                best_tid = tid
                best_extra = extra
                best_encoded = encoded
                best_freq = freq
                best_padding = padding
        # header per block: tid(1) flags(1) orig_len(2) extra_len(1) padding(1) freq(512) enc_len(4) extra(var) encoded(var)
        out.append(best_tid)
        out.append(0) # flags reserved
        out.extend(struct.pack(">H", len(block)))
        out.append(len(best_extra))
        out.append(best_padding)
        for f in best_freq:
            out.extend(struct.pack(">H", min(f,65535)))
        out.extend(struct.pack(">I", len(best_encoded)))
        out.extend(best_extra)
        out.extend(best_encoded)
    return bytes(out)

def decompress(data: bytes) -> bytes:
    if not data.startswith(MAGIC):
        raise ValueError("Invalid magic")
    pos=4
    version=data[pos]; pos+=1
    num_blocks=struct.unpack(">I", data[pos:pos+4])[0]; pos+=4
    out=bytearray()
    for _ in range(num_blocks):
        tid=data[pos]; pos+=1
        flags=data[pos]; pos+=1
        orig_len=struct.unpack(">H", data[pos:pos+2])[0]; pos+=2
        extra_len=data[pos]; pos+=1
        padding=data[pos]; pos+=1
        freq=[struct.unpack(">H", data[pos+i*2:pos+i*2+2])[0] for i in range(256)]
        pos+=512
        enc_len=struct.unpack(">I", data[pos:pos+4])[0]; pos+=4
        extra=data[pos:pos+extra_len]; pos+=extra_len
        encoded=data[pos:pos+enc_len]; pos+=enc_len
        # transformed length == original length (all transforms size-preserving)
        transformed = huffman_decode_block(encoded, freq, padding, orig_len)
        _, enc_fn, dec_fn = TRANSFORMS[tid]
        final = dec_fn(transformed, extra)
        # ensure length
        if len(final) != orig_len:
            # trim/pad if needed due to empty block edge
            final = final[:orig_len]
        out.extend(final)
    return bytes(out)

# Alias for benchmark
compress_simple = compress
decompress_simple = decompress
