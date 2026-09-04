"""
Layer 2: Hierarchical Grammar Compression (Re-Pair)
Theory: Dictionary only finds exact repeats. Grammar finds recursive, nested patterns.
This beats RLE and LZ for structured data.
"""
from collections import Counter

def repair_compress(data: bytes, max_iters=1000):
    """
    Re-Pair algorithm: iteratively replace most frequent pair with new symbol.
    Returns (compressed_sequence: list[int], rules: dict[new_sym -> (a,b)], original_alphabet_size)
    Symbols 0-255 are bytes, 256+ are grammar rules.
    """
    if len(data) < 4:
        return list(data), {}
    seq = list(data)
    rules = {}
    next_sym = 256
    # Limit next_sym to < 65535 for 2-byte storage
    for _ in range(max_iters):
        if len(seq) < 2:
            break
        # count pairs
        pair_counts = Counter()
        for i in range(len(seq)-1):
            pair_counts[(seq[i], seq[i+1])] += 1
        # find most frequent pair with count >1
        most_common = pair_counts.most_common(1)
        if not most_common or most_common[0][1] < 2:
            break
        pair, cnt = most_common[0]
        # create new rule
        new_sym = next_sym
        next_sym += 1
        if next_sym > 60000:
            break
        rules[new_sym] = pair
        # replace all non-overlapping occurrences left-to-right
        new_seq = []
        i=0
        while i < len(seq):
            if i < len(seq)-1 and (seq[i], seq[i+1]) == pair:
                new_seq.append(new_sym)
                i+=2
            else:
                new_seq.append(seq[i])
                i+=1
        seq = new_seq
        # early stop if no reduction
        if len(seq) >= len(data)*0.9 and len(rules)>20:
            # still continue but check
            pass
    return seq, rules

def repair_decompress(seq, rules):
    """Expand grammar rules recursively"""
    # iterative expansion: replace symbols >255 until all <256
    # Need to expand in reverse order of creation (largest first)
    # Since rules may reference other rules, we need recursive expansion
    # Build expansion cache
    cache = {}
    def expand(sym):
        if sym < 256:
            return [sym]
        if sym in cache:
            return cache[sym]
        a,b = rules[sym]
        res = expand(a) + expand(b)
        cache[sym]=res
        return res
    out = bytearray()
    for sym in seq:
        out.extend(expand(sym))
    return bytes(out)

def estimate_grammar_benefit(data: bytes):
    """Quick estimate: if Re-Pair reduces length significantly, it's useful"""
    seq, rules = repair_compress(data, max_iters=50)  # quick
    # cost: seq as 2 bytes per symbol if >255 else 1, plus rules (4 bytes each)
    cost_seq = sum(2 if s>255 else 1 for s in seq)
    cost_rules = len(rules)*4
    return cost_seq + cost_rules, len(data)

# For experiment: we can use grammar as optional layer before Huffman
# If benefit not >10%, skip it.
