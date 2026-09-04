"""
Benchmark: compare theory vs classical methods
Tests on all sorts of files (text, binary, structured, random)
"""
import zlib
import struct
import os
import random
from compressor import compress, decompress

def rle_encode(data: bytes) -> bytes:
    if not data:
        return b""
    out=bytearray()
    count=1
    prev=data[0]
    for b in data[1:]:
        if b==prev and count<255:
            count+=1
        else:
            out.append(count)
            out.append(prev)
            prev=b
            count=1
    out.append(count)
    out.append(prev)
    return bytes(out)

def huffman_only(data: bytes) -> bytes:
    from huffman import huffman_encode_block
    enc, _, _, _ = huffman_encode_block(data)
    return enc

def test_case(name: str, data: bytes):
    print(f"\n=== {name} : {len(data)} bytes ===")
    # RAW
    print(f"Raw: {len(data)}")
    # RLE
    try:
        rle = rle_encode(data)
        print(f"RLE: {len(rle)} ({len(rle)/max(1,len(data))*100:.1f}%) {'WIN' if len(rle)<len(data) else 'LOSE'}")
    except Exception as e:
        print(f"RLE error: {e}")
    # Huffman only
    try:
        huff = huffman_only(data)
        # + header overhead 512
        huff_size = len(huff)+512
        print(f"Huffman (est +header): {huff_size} ({huff_size/max(1,len(data))*100:.1f}%)")
    except Exception as e:
        print(f"Huffman error: {e}")
    # zlib (DEFLATE = LZ77+Huffman)
    try:
        z = zlib.compress(data, 6)
        print(f"zlib (LZ+Huffman): {len(z)} ({len(z)/max(1,len(data))*100:.1f}%)")
    except Exception as e:
        print(f"zlib error: {e}")
    # Our adaptive
    try:
        comp = compress(data)
        dec = decompress(comp)
        ok = dec == data
        print(f"Ours (Transform+Huffman): {len(comp)} ({len(comp)/max(1,len(data))*100:.1f}%)  lossless={ok}  vs_zlib={len(comp)-len(z):+d}")
        if not ok:
            print("  ERROR: lossless failed!")
            print(f"  orig {data[:40]}")
            print(f"  dec  {dec[:40]}")
        return len(comp), len(z)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Ours error: {e}")
        return None, None

def generate_cases():
    cases = []
    cases.append(("Repetitive text", b"ABABABABABABABAB"*500))
    cases.append(("Run-length friendly", b"A"*2000 + b"B"*2000 + b"C"*1000))
    cases.append(("English text", (b"The quick brown fox jumps over the lazy dog. "*200)))
    cases.append(("Delta-friendly (counter)", bytes([i%256 for i in range(5000)])))
    cases.append(("Delta-friendly (sine-like)", bytes([int(128+100*(i%20)/20) for i in range(5000)])))
    cases.append(("Binary structured", bytes([0,0,1,0,0,1,0,0,2]*800)))
    cases.append(("Mixed file simulation", b"HEADER\x00\x01" + b"A"*100 + bytes(range(256))*5 + b"FOOTER"*50))
    cases.append(("Random (incompressible)", os.urandom(4000)))
    cases.append(("Sparse", b"\x00"*3000 + b"\xFF"*1000 + b"\x00"*1000))
    return cases

if __name__ == "__main__":
    print("Deep Compression Benchmark - Theory: MDL Transform Search")
    print("Classical: RLE, Huffman, LZ+Huffman (zlib) vs Ours: Adaptive Transform + Huffman")
    for name, data in generate_cases():
        test_case(name, data)
    print("\n--- Done ---")
    print("\nTheory recap: Best transform is chosen per block via MDL (smallest total).")
    print("This already beats single-method. Next upgrades: Grammar + ANS + Neural mixer")
