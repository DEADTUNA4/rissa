import zlib
from transforms import TRANSFORMS
from huffman import huffman_encode_block

def transform_zlib_best(data, block_size=4096):
    # Try transforms + zlib, pick best per block
    out_parts=[]
    for i in range(0, len(data), block_size):
        block=data[i:i+block_size]
        best=None
        best_tid=0
        best_extra=b""
        for tid,(name,enc,dec) in TRANSFORMS.items():
            if tid==3 and len(block)>2048:
                continue
            transformed, extra = enc(block)
            if transformed is None:
                continue
            comp = zlib.compress(transformed, 9)
            size = len(comp)+len(extra)+1  # +1 for tid
            if best is None or size < len(best):
                best=comp
                best_tid=tid
                best_extra=extra
        out_parts.append((best_tid, best_extra, best))
    # reconstruct size estimate
    total = 4+1+4  # magic+version+numblocks
    for tid, extra, comp in out_parts:
        total += 1+1+2+1+4+len(extra)+len(comp)  # simplified header
    return total, out_parts

def test(name, data):
    print(f"\n{name} {len(data)} bytes")
    zlib_only = len(zlib.compress(data,9))
    print(f"  zlib only: {zlib_only} ({zlib_only/len(data)*100:.1f}%)")
    # our huffman only earlier
    from huffman import estimate_huffman_size
    huff_est = estimate_huffman_size(data)
    print(f"  huffman est: {huff_est}")
    # transform+zlib
    total, parts = transform_zlib_best(data)
    print(f"  transform+zlib (theory v2): {total} ({total/len(data)*100:.1f}%) vs zlib {total - zlib_only:+d}")
    # which transform won?
    if parts:
        from collections import Counter
        tids = [p[0] for p in parts]
        c=Counter(tids)
        names={0:"RAW",1:"DELTA",2:"XOR",3:"BWT_MTF"}
        print(f"    chosen transforms: {dict((names[k],v) for k,v in c.items())}")

cases=[
    ("ABAB repeat", b"ABABABAB"*1000),
    ("Counter 0..255", bytes([i%256 for i in range(5000)])),
    ("Incremental small steps", bytes([100 + (i%10) for i in range(5000)])),
    ("English", b"The quick brown fox jumps over "*500),
    ("Binary structured", bytes([0,0,1,0,0,1]*1000)),
    ("Mixed", b"HEADER" + bytes(range(256))*10 + b"DATA"*500),
    ("Random", __import__("os").urandom(4000)),
]
for n,d in cases:
    test(n,d)
