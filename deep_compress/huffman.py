"""
Huffman entropy coder - replaces basic frequency coding with optimal prefix codes.
Used as Layer 4 in the theory. Will be upgraded to ANS later.
"""
import heapq
import struct
from collections import Counter

class Node:
    __slots__ = ('freq','symbol','left','right')
    def __init__(self, freq, symbol=None, left=None, right=None):
        self.freq=freq
        self.symbol=symbol
        self.left=left
        self.right=right
    def __lt__(self, other):
        return self.freq < other.freq

def build_tree(freq):
    heap = []
    for sym, f in enumerate(freq):
        if f > 0:
            heapq.heappush(heap, Node(f, symbol=sym))
    if len(heap) == 0:
        return None
    if len(heap) == 1:
        # single symbol case
        only = heapq.heappop(heap)
        return Node(only.freq, left=only, right=Node(0, symbol=(only.symbol+1)%256))
    while len(heap) > 1:
        a = heapq.heappop(heap)
        b = heapq.heappop(heap)
        heapq.heappush(heap, Node(a.freq+b.freq, left=a, right=b))
    return heap[0]

def build_codes(node, prefix="", codes=None):
    if codes is None:
        codes = {}
    if node.symbol is not None:
        codes[node.symbol] = prefix if prefix != "" else "0"
    else:
        if node.left:
            build_codes(node.left, prefix+"0", codes)
        if node.right:
            build_codes(node.right, prefix+"1", codes)
    return codes

def huffman_encode_block(data: bytes):
    """Returns (encoded_bytes, freq_table, padding_bits, codes)"""
    if len(data)==0:
        return b"", [0]*256, 0, {}
    freq = [0]*256
    for b in data:
        freq[b]+=1
    tree = build_tree(freq)
    codes = build_codes(tree)
    # build bitstring
    bit_str = "".join(codes[b] for b in data)
    padding = (8 - len(bit_str) % 8) % 8
    bit_str += "0"*padding
    out = bytearray()
    for i in range(0, len(bit_str), 8):
        out.append(int(bit_str[i:i+8], 2))
    return bytes(out), freq, padding, codes

def huffman_decode_block(encoded: bytes, freq, padding, original_len):
    if original_len==0:
        return b""
    tree = build_tree(freq)
    if tree is None:
        return b""
    # convert to bitstring
    bit_str = "".join(f"{b:08b}" for b in encoded)
    if padding:
        bit_str = bit_str[:-padding]
    out = bytearray()
    node = tree
    for bit in bit_str:
        node = node.left if bit=="0" else node.right
        if node.symbol is not None:
            out.append(node.symbol)
            if len(out)==original_len:
                break
            node = tree
    return bytes(out)

def estimate_huffman_size(data: bytes):
    """Fast estimate without building bitstream - sum freq * codelen"""
    if len(data)==0:
        return 0
    freq = [0]*256
    for b in data:
        freq[b]+=1
    tree = build_tree(freq)
    codes = build_codes(tree)
    total_bits = sum(freq[sym]*len(code) for sym, code in codes.items())
    # header overhead: 256*2 + 2 bytes approx
    overhead_bits = 512*8
    return (total_bits + overhead_bits + 7)//8

# --- simple ANS-like range coder placeholder (for theory) ---
# We keep Huffman for now; ANS would replace this with direct prob coding
# ANS achieves ~0.1% overhead vs Huffman's up to ~12% on skewed data
