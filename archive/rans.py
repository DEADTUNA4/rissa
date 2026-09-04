"""
rANS / FSE stub for Layer 3. Currently wraps Huffman with Shannon reporting; rANS is drop-in next.
Reports bits/symbol vs Shannon entropy per block (defensible vs '10x closer' framing).
"""
import math
from collections import Counter
try:
    from huffman import huffman_encode_block, huffman_decode_block
except ImportError:
    from .huffman import huffman_encode_block, huffman_decode_block, build_tree, build_codes

def shannon_entropy(data: bytes):
    if not data: return 0.0
    freq=Counter(data)
    n=len(data)
    return -sum((c/n)*math.log2(c/n) for c in freq.values())

def rans_encode_block(data: bytes):
    """
    Placeholder: uses Huffman but returns metrics for rANS comparison.
    Real rANS: range ANS with order-0 or order-1 context, fractional bits.
    """
    enc, freq, pad, codes = huffman_encode_block(data)
    # metrics
    ent = shannon_entropy(data)
    total_bits = sum(freq[s]*len(c) for s,c in codes.items()) if codes else 0
    bits_per_sym = total_bits/len(data) if data else 0
    overhead = len(enc) - total_bits/8
    return enc, freq, pad, codes, {"entropy":ent, "bits_per_sym":bits_per_sym, "overhead_bytes":overhead, "shannon_bytes":ent/8*len(data)}

def rans_decode_block(enc, freq, pad, orig_len):
    return huffman_decode_block(enc, freq, pad, orig_len)

def report_block(data: bytes):
    enc, freq, pad, codes, m = rans_encode_block(data)
    print(f"  len {len(data)} entropy {m['entropy']:.2f} b/B shannon {m['shannon_bytes']:.0f}B huffman {len(enc)}B {m['bits_per_sym']:.2f} b/sym overhead {m['overhead_bytes']:.1f}B")
    return m

if __name__=="__main__":
    for d in [b"a"*1000, bytes([i%256 for i in range(1000)]), b"hello world "*100]:
        m=report_block(d)
