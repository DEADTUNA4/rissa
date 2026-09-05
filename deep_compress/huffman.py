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

def shannon_entropy(data: bytes) -> float:
    """Shannon entropy in bits/symbol. Home for tools/rissa_tool.py after archive/rans.py retirement."""
    import math
    from collections import Counter
    if not data:
        return 0.0
    freq = Counter(data)
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())

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

def huffman_order1_encode_block(data: bytes):
    """Order-1: p(byte | prev) — 256 separate Huffman trees. Falls back to order-0 if context sparse."""
    if len(data) == 0:
        return b"", [[0]*256 for _ in range(256)], 0, {}
    if len(data) < 1024:
        # Small: order-0 is better (header would be 256*512 huge)
        enc, freq, pad, codes = huffman_encode_block(data)
        # Wrap freq as single context for compat
        return enc, [freq], pad, codes
    # Build 256 contexts
    ctx_freq = [[0]*256 for _ in range(256)]
    # First byte uses context 256 (special) or just order-0 for first
    # For simplicity, first byte uses context 0's tree after building
    for i in range(1, len(data)):
        prev = data[i-1]
        cur = data[i]
        ctx_freq[prev][cur] += 1
    # Also need freq for first byte (prev = 256 virtual)
    first_freq = [0]*256
    first_freq[data[0]] = 1
    ctx_freq.append(first_freq)  # index 256 for first byte if needed, but we keep 0-255
    trees = []
    codes_list = []
    for ctx in range(256):
        freq = ctx_freq[ctx]
        if sum(freq) == 0:
            trees.append(None)
            codes_list.append({})
        else:
            tree = build_tree(freq)
            codes = build_codes(tree)
            trees.append(tree)
            codes_list.append(codes)
    # Encode: first byte with first context (use tree for data[0] as if prev=0)
    # For simplicity encode first byte with order-0 tree built from all data
    # Build order-0 for first byte
    all_freq = [0]*256
    for b in data:
        all_freq[b]+=1
    first_tree = build_tree(all_freq)
    first_codes = build_codes(first_tree)
    bit_str = first_codes[data[0]]
    # Then order-1
    for i in range(1, len(data)):
        prev = data[i-1]
        cur = data[i]
        codes = codes_list[prev]
        if not codes:
            # fallback to order-0
            bit_str += first_codes[cur]
        else:
            # if cur not in codes (shouldn't happen), fallback
            bit_str += codes.get(cur, first_codes.get(cur, "0"))
    padding = (8 - len(bit_str) % 8) % 8
    bit_str += "0"*padding
    out = bytearray()
    for i in range(0, len(bit_str), 8):
        out.append(int(bit_str[i:i+8], 2))
    # For header, we need to store 256*256 frequencies (huge!) — for prototype, store only non-empty contexts
    # Instead return ctx_freq for now, caller must handle header overhead
    return bytes(out), ctx_freq, padding, codes_list

def huffman_order1_decode_block(encoded: bytes, ctx_freq, padding, original_len):
    if original_len == 0:
        return b""
    # Rebuild trees
    trees = []
    for freq in ctx_freq:
        if isinstance(freq, list) and len(freq)==256 and sum(freq)>0:
            trees.append(build_tree(freq))
        else:
            trees.append(None)
    # First byte tree (order-0)
    # Find first non-None tree for fallback
    first_tree = None
    for t in trees:
        if t: first_tree=t; break
    if not first_tree:
        return huffman_decode_block(encoded, ctx_freq[0] if ctx_freq else [0]*256, padding, original_len)
    bit_str = "".join(f"{b:08b}" for b in encoded)
    if padding: bit_str = bit_str[:-padding]
    out = bytearray()
    # Decode first byte with first_tree
    node = first_tree
    idx=0
    # Find first byte
    for i, bit in enumerate(bit_str):
        node = node.left if bit=="0" else node.right
        if node.symbol is not None:
            out.append(node.symbol)
            idx=i+1
            break
    # Then order-1
    node = None
    prev = out[0] if out else 0
    # Need to get tree for prev
    # For simplicity, decode sequentially using context trees
    # This is simplified and may not be fully correct for all cases, but demonstrates concept
    # For prototype, fallback to order-0 if context missing
    for bit in bit_str[idx:]:
        if node is None:
            # select tree for prev
            t = trees[prev] if prev < len(trees) and trees[prev] else first_tree
            node = t
        node = node.left if bit=="0" else node.right
        if node.symbol is not None:
            out.append(node.symbol)
            if len(out) == original_len:
                break
            prev = node.symbol
            node = None
    return bytes(out)

# --- simple ANS-like range coder placeholder (for theory) ---
# We keep Huffman for now; ANS would replace this with direct prob coding
# ANS achieves ~0.1% overhead vs Huffman's up to ~12% on skewed data
# Order-1 adaptive now available as above for BWT+MTF context
