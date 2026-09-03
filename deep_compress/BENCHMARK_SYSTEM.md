# Benchmark System — rissa

**Model:** ASUS TUF Gaming FX504GE  
**CPU:** Intel Core i7-8750H @ 2.2 GHz (6 cores, 12 threads)  
**GPU:** NVIDIA GeForce GTX 1050 Ti (not used)  
**RAM:** 32 GB DDR4 (32,623 MB total)  
**OS:** Windows 11 Pro, build 26200, 64-bit  
**Python:** 3.13.14

**Storage**
- System drive (C:): Micron 1100 256 GB SATA SSD
- Secondary drive: Seagate ST2000LM007 2 TB HDD — **benchmark files stored here** (reflects typical datacenter HDD)
- Removable: Kingston DataTraveler 3.0 (123 GB), Generic Flash Disk (31 GB) — not used

**Benchmark notes — rissa**
- All test files on Seagate HDD; compression ratio is storage-independent, speed may be I/O-bound.
- For fair MB/s, rissa benches use **in-memory** `compress_with_dict(data)` (no disk I/O) + wall-clock `time.perf_counter()`; disk I/O is noted separately.
- Multiprocessing uses up to **12 threads** (`concurrent.futures.ProcessPoolExecutor(max_workers=12)`) — scales with 6c/12t, limited by 32GB RAM and CPU load.
- Block size 1M (default) → 4M (max) — 1M balances 12-thread pool (100MB file → 100 tasks) vs 4M reduces tasks but larger dict window (64M). Header 0.05% at 1M.
- Python 3.13.14 GIL + `lzma` single-threaded; rissa parallelizes **per-block transform selection** (16T) + backend, while `xz -9` is single-threaded — expect near-linear speedup on 12 threads for >4 blocks.

**Reproduce on this system**
```bash
python deep_compress/final_bench.py          # 128K MDL, 16T, 3 runs ± stdev, in-memory
python deep_compress/compressor_v4.py        # 1M/4M block, preset_dict, two-pass
python tools/rissa_tool.py gui               # GUI shows MB/s + hist
```
