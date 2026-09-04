#!/usr/bin/env python3
"""
rissa - Jorma Rissanen MDL 1978 - https://rissa.web.app
CLI: rissa input.bin -o output.rissa  |  rissa -d input.rissa -o output.bin
"""
import argparse, sys, pathlib, os
sys.path.insert(0, os.path.dirname(__file__))

from compressor_v3 import compress_with_dict, decompress_with_dict, BLOCK_SIZE_64K, BLOCK_SIZE_128K, MAGIC

def main():
    p=argparse.ArgumentParser(prog="rissa", description="rissa - Adaptive MDL Compressor (Rissanen 1978) - https://rissa.web.app")
    p.add_argument("input", nargs="?", help="input file (or stdin if not given)")
    p.add_argument("-o","--output", required=True, help="output file (.rissa)")
    p.add_argument("-d","--decompress", action="store_true", help="decompress")
    p.add_argument("--block", type=int, default=65536, choices=[4096,16384,65536,131072], help="block size (default 64K)")
    p.add_argument("--dict", action="store_true", help="enable shared dict 1MB->64KB MDL-gated")
    p.add_argument("--backend", default="zstd", choices=["zstd","lzma","zlib","huffman"], help="backend")
    p.add_argument("--level", type=int, default=None, help="level (zstd 1-22, xz 0-9)")
    p.add_argument("--stream", action="store_true", help="streaming mode for large files (for block in stream)")
    args=p.parse_args()

    if args.decompress:
        data=pathlib.Path(args.input).read_bytes() if args.input != "-" else sys.stdin.buffer.read()
        out=decompress_with_dict(data)
        if args.output == "-":
            sys.stdout.buffer.write(out)
        else:
            pathlib.Path(args.output).write_bytes(out)
            print(f"rissa decompressed {len(data)} -> {len(out)} -> {args.output}", file=sys.stderr)
    else:
        data=pathlib.Path(args.input).read_bytes() if args.input != "-" else sys.stdin.buffer.read()
        if args.stream:
            # streaming via file handles
            import io
            bio_in=io.BytesIO(data)
            bio_out=io.BytesIO()
            from compressor_v3 import compress_stream
            compress_stream(bio_in, bio_out, backend=args.backend, level=args.level, block_size=args.block, use_dict=args.dict)
            out=bio_out.getvalue()
        else:
            out, hist, d = compress_with_dict(data, backend=args.backend, level=args.level, block_size=args.block, use_dict=args.dict)
            print(f"rissa {len(data)} -> {len(out)} {len(out)/len(data)*100:.1f}% hist {dict(hist.most_common(3))} dict {len(d) if d else 0}", file=sys.stderr)
        if args.output == "-":
            sys.stdout.buffer.write(out)
        else:
            pathlib.Path(args.output).write_bytes(out)

if __name__=="__main__":
    main()
