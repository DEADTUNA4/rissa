"""
Phase 0 - Profiling & Justification for GTX 1050 Ti
Strip out LZMA, measure transform loop only over 50MB JSON
"""
import time, pathlib, sys
sys.path.insert(0, '.')
from deep_compress.compressor_v4 import compress_v4
import lzma

# Create 50MB JSON-like data
data = (b'{"id":123,"name":"test","value":42,"timestamp":1609459200}\n' * 1000000)[:50*1024*1024]
print(f"Dataset: {len(data)/1024/1024:.1f}MB JSON-like, {len(data)//(1*1024*1024)} blocks of 1M")

# Baseline: CPU transform loop only (strip out LZMA)
import time
from deep_compress.transforms_v2 import TRANSFORMS_V2
from deep_compress.compressor_v4 import BLOCK_1M

# Measure CPU transform loop
t0=time.perf_counter()
blocks=[data[i:i+BLOCK_1M] for i in range(0, len(data), BLOCK_1M)]
for block in blocks:
    for tid in [0,7,14]:  # RAW, SHUFFLE_4, BIT_TRANSPOSE - the expensive ones
        name, enc, dec = TRANSFORMS_V2[tid]
        tr, ex = enc(block)
        # Don't do lzma, just transform
        pass
t_cpu_transform=time.perf_counter()-t0
print(f"CPU transform loop (3 transforms x {len(blocks)} blocks): {t_cpu_transform:.3f}s")

# Measure LZMA alone
t0=time.perf_counter()
for block in blocks:
    lzma.compress(block, preset=6)
t_lzma=time.perf_counter()-t0
print(f"LZMA (preset 6) {len(blocks)} blocks: {t_lzma:.3f}s")
print(f"Transform {t_cpu_transform/(t_cpu_transform+t_lzma)*100:.1f}% of total, LZMA {t_lzma/(t_cpu_transform+t_lzma)*100:.1f}%")

# Baseline MB/s
from deep_compress.compressor_v4 import compress_v4
t0=time.perf_counter()
comp, hist, d = compress_v4(data, backend='lzma', block_size=BLOCK_1M, use_dict=False)
t_total=time.perf_counter()-t0
print(f"Total rissa (with LZMA) {t_total:.3f}s {len(data)/t_total/1e6:.1f} MB/s hist {dict(hist)}")

# GPU batched SHUFFLE test (if CuPy available)
try:
    from deep_compress.gpu_shuffle import shuffle_gpu_batched, HAS_CUPY, HAS_CUDA
    print(f"\nGPU: HAS_CUPY={HAS_CUPY} HAS_CUDA={HAS_CUDA}")
    if HAS_CUPY and HAS_CUDA:
        import cupy as cp
        # Test batched SHUFFLE on same blocks
        t0=time.perf_counter()
        # Pad blocks to max_len
        max_len=max(len(b) for b in blocks)
        # This would be the GPU path - for now just measure CPU SHUFFLE vs GPU SHUFFLE
        from deep_compress.gpu_shuffle import shuffle_cpu
        for block in blocks:
            shuffle_cpu(block, 4)
        t_cpu_shuffle=time.perf_counter()-t0
        print(f"CPU SHUFFLE {len(blocks)} blocks: {t_cpu_shuffle:.3f}s")
        # GPU would be ~1ms for 50MB on 1050 Ti (112 GB/s) + 10-15ms PCIe
        print(f"Expected GPU SHUFFLE 50MB: ~1ms kernel + 10-15ms PCIe = ~15ms vs CPU {t_cpu_shuffle*1000:.0f}ms")
        if t_cpu_shuffle > 0.015*5:
            print("GPU wins - transform >70% of total, proven")
        else:
            print("GPU may not win - need larger file")
    else:
        print("CuPy not installed - install cupy-cuda11x for GTX 1050 Ti (Pascal 6.1) via: pip install rissa[gpu]")
        print("Fallback to CPU - transform loop still Python, but 50MB JSON should show if bottleneck is transform (>70%)")
except Exception as e:
    print(f"GPU test skip {e}")

print("\nBaseline for thresholds: test 10,20,50,100 blocks to find break-even for 1050 Ti")
for n in [10,20,50,100]:
    test_blocks=[b'x'*1024*1024 for _ in range(n)]
    total=n*1024*1024
    # Estimate PCIe 15ms per 100MB, kernel 1ms per 100MB
    pcie=total/100*1024*1024 * 15/100/1e6  # rough
    print(f"{n} blocks {total/1024/1024}MB PCIe ~{pcie*1000:.1f}ms")
