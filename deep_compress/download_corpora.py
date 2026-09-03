"""
Download Phase 3 real corpora: NOAA, Loghub, Yellow Taxi
Uses curl with resume, fallback to synthetic if fail.
"""
import os, pathlib, subprocess, sys

CORPORA_DIR = pathlib.Path("deep_compress/corpora")
CORPORA_DIR.mkdir(parents=True, exist_ok=True)

def curl_download(url, dest, max_time=600):
    dest=str(dest)
    # use curl with resume -C -
    cmd=[r"C:\Windows\System32\curl.exe", "-L", "-C", "-", "-o", dest, url, "--connect-timeout", "30", "--max-time", str(max_time)]
    print(f"Downloading {url} -> {dest}")
    try:
        subprocess.run(cmd, check=False, timeout=max_time+10)
        if os.path.exists(dest):
            sz=os.path.getsize(dest)
            print(f"  done {sz} bytes")
            return sz>1000
    except Exception as e:
        print(f"  fail {e}")
    return False

# 1. Yellow Taxi - NYC TLC (parquet, ~30MB for 2023-01, good columnar test for SHUFFLE/BIT_TRANSPOSE)
yt_url="https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2023-01.parquet"
yt_dest=CORPORA_DIR/"yellow_tripdata_2023-01.parquet"
# also try smaller 2024 sample
# 2. Loghub - HDFS log (2.6MB) and Apache (4.7MB) from loghub repo via github raw
# Use direct github archive for 2 specific logs
loghub_urls=[
    ("https://raw.githubusercontent.com/logpai/loghub/master/Apache/Apache_2k.log", CORPORA_DIR/"Apache_2k.log"),
    ("https://raw.githubusercontent.com/logpai/loghub/master/HDFS/HDFS_2k.log", CORPORA_DIR/"HDFS_2k.log"),
    # fallback: full zip if needed
    # ("https://github.com/logpai/loghub/archive/refs/heads/master.zip", CORPORA_DIR/"loghub.zip"),
]
# 3. NOAA - Global Hourly sample - use NOAA public: small csv for 2023
# Try NOAA GHCN or ISD sample: use a known small NOAA csv from NCEI
noaa_urls=[
    ("https://www.ncei.noaa.gov/data/global-hourly/access/2023/01001099999.csv", CORPORA_DIR/"noaa_01001099999.csv"),
    # fallback: synthetic will be used if all fail
]

print("=== Phase 3 download ===")
ok_yt=curl_download(yt_url, yt_dest, max_time=600)
for url, dest in loghub_urls:
    curl_download(url, dest, max_time=60)
for url, dest in noaa_urls:
    curl_download(url, dest, max_time=60)

print("\n=== Summary ===")
for p in sorted(CORPORA_DIR.iterdir()):
    print(f"{p.name:40} {p.stat().st_size:10} bytes")
# if no real files, note synthetic fallback
if not any(CORPORA_DIR.iterdir()):
    print("No real corpora downloaded - will use synthetic generators")
else:
    print("Real corpora ready for ingest_phase3.py")
