#!/usr/bin/env python3
"""
rissa tool - Desktop GUI + CLI for rissa compression
https://rissa.web.app - Jorma Rissanen MDL 1978

Usage CLI:
  python tools/rissa_tool.py compress input.bin -o output.rissa --block 131072 --dict
  python tools/rissa_tool.py decompress input.rissa -o output.bin
  python tools/rissa_tool.py gui   # launch Tkinter GUI

GUI: drag-drop or file picker, shows ratio, bits/sym vs Shannon, transform histogram.
"""
import argparse, sys, pathlib, os, time, logging, traceback
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "deep_compress"))

DISCORD_URL = "https://discord.gg/wzpwcCv92j"

def log_dir():
    """Writable log folder: LocalAppData first (exe dir may be read-only)."""
    cands = []
    lad = os.environ.get("LOCALAPPDATA")
    if lad:
        cands.append(pathlib.Path(lad) / "rissa" / "logs")
    try:
        cands.append(pathlib.Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent / "logs")
    except Exception:
        pass
    import tempfile
    cands.append(pathlib.Path(tempfile.gettempdir()) / "rissa-logs")
    for p in cands:
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            continue
    return pathlib.Path(".")

_LOGGER = None
def get_logger():
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER
    lg = logging.getLogger("rissa")
    lg.setLevel(logging.INFO)
    try:
        from logging.handlers import RotatingFileHandler
        fh = RotatingFileHandler(str(log_dir() / "rissa.log"), maxBytes=262144, backupCount=3, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        lg.addHandler(fh)
    except Exception:
        pass
    _LOGGER = lg
    return lg

def log_path():
    return str(log_dir() / "rissa.log")

def report_bug(msg):
    """Log an error and tell the user exactly where to paste it."""
    get_logger().error(msg)
    return f"Logged to {log_path()} — paste it on Discord: {DISCORD_URL}"

def _excepthook(typ, val, tb):
    try:
        get_logger().critical("UNCAUGHT: " + "".join(traceback.format_exception(typ, val, tb)))
    except Exception:
        pass
    sys.__excepthook__(typ, val, tb)
    print(f"\nBUG? {report_bug(str(val))}", file=sys.stderr)
sys.excepthook = _excepthook

from deep_compress.compressor_v3 import compress_with_dict, decompress_with_dict
from deep_compress.huffman import shannon_entropy

def cli_compress(inp, out, block, use_dict, backend="zstd", fast=False):
    lg = get_logger()
    lg.info(f"compress in={inp} out={out} block={block} dict={use_dict} backend={backend} fast={fast} frozen={getattr(sys,'frozen',False)}")
    data = pathlib.Path(inp).read_bytes()
    ent = shannon_entropy(data) if data else 0
    t0=time.perf_counter()
    comp, hist, d = compress_with_dict(data, backend=backend, block_size=block, use_dict=use_dict, fast=fast)
    t=time.perf_counter()-t0
    pathlib.Path(out).write_bytes(comp)
    bits = len(comp)*8/len(data) if data else 0
    print(f"rissa compress: {len(data)} -> {len(comp)} {len(comp)/len(data)*100:.1f}% {bits:.2f} b/sym ent {ent:.2f} time {t:.2f}s hist {dict(hist.most_common(3))} dict {len(d) if d else 0} fast={fast} -> {out}")
    lg.info(f"compress done {len(data)}->{len(comp)} {t:.2f}s hist={dict(hist.most_common(3))}")

def cli_decompress(inp, out):
    lg = get_logger()
    lg.info(f"decompress in={inp} out={out}")
    data = pathlib.Path(inp).read_bytes()
    t0=time.perf_counter()
    dec = decompress_with_dict(data)
    t=time.perf_counter()-t0
    pathlib.Path(out).write_bytes(dec)
    print(f"rissa decompress: {len(data)} -> {len(dec)} time {t:.2f}s -> {out}")
    lg.info(f"decompress done {len(data)}->{len(dec)} {t:.2f}s")

def cli_doctor():
    import platform
    try:
        import rissa
        rissa_ver = getattr(rissa, "__version__", "unknown")
    except Exception as e:
        rissa_ver = f"import failed: {e}"
    print(f"rissa {rissa_ver} on {platform.system()} {platform.machine()} {platform.python_version()}")
    for mod, flag in [("rissa.c_shuffle", "HAS_C_SHUFFLE"), ("rissa.c_bit", "HAS_C_BIT"), ("rissa.c_delta", "HAS_C_DELTA"), ("rissa.c_trans", "HAS_C_TRANS"), ("rissa.c_huff", "HAS_C_HUFF"), ("rissa.c_stat", "HAS_C_STAT")]:
        try:
            __import__(mod)
            print(f"  {flag}=True ({mod} loads)")
        except Exception as e:
            print(f"  {flag}=False ({mod}: {type(e).__name__}: {e})")
    try:
        import deep_compress.transforms_v2 as T
        print(f"  transforms_v2 flags: SHUFFLE={T.HAS_C_SHUFFLE} BIT={T.HAS_C_BIT} DELTA={T.HAS_C_DELTA} TRANS={T.HAS_C_TRANS}")
    except Exception as e:
        print(f"  transforms_v2: import failed: {e}")
    try:
        import deep_compress.huffman as H
        print(f"  huffman flags: HUFF={H.HAS_C_HUFF} STAT={H.HAS_C_STAT}")
    except Exception as e:
        print(f"  huffman: import failed: {e}")
    for mod in ["zstandard", "lzma", "zlib", "bz2"]:
        try:
            __import__(mod)
            print(f"  backend {mod}: available")
        except Exception as e:
            print(f"  backend {mod}: MISSING ({e})")
    import sys
    print(f"  frozen={getattr(sys, 'frozen', False)}")
    print(f"  logs: {log_path()}")
    print(f"  bugs: paste the log on Discord: {DISCORD_URL}")
    get_logger().info("doctor run")

def launch_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    root=tk.Tk()
    root.title("rissa - Rissanen MDL 1978")
    root.geometry("560x420")
    # style
    try:
        from tkinter import ttk
        style=ttk.Style()
        style.theme_use("clam")
    except: pass

    # header
    hdr=tk.Label(root, text="rissa", font=("Segoe UI", 20, "bold"))
    hdr.pack(pady=8)
    sub=tk.Label(root, text="Context-Selecting Compression  •  rissa.web.app", fg="#64748b")
    sub.pack()

    # file pick
    frm=tk.Frame(root)
    frm.pack(pady=12, fill="x", padx=16)
    var_in=tk.StringVar()
    var_out=tk.StringVar()
    def pick_in():
        p=filedialog.askopenfilename()
        if p:
            var_in.set(p)
            # auto suggest output
            pp=pathlib.Path(p)
            if pp.suffix==".rissa":
                var_out.set(str(pp.with_suffix("")))
            else:
                var_out.set(str(pp)+".rissa")
    def pick_out():
        p=filedialog.asksaveasfilename(defaultextension=".rissa")
        if p: var_out.set(p)
    tk.Label(frm, text="Input:").grid(row=0, column=0, sticky="w")
    tk.Entry(frm, textvariable=var_in, width=40).grid(row=0, column=1, padx=6)
    tk.Button(frm, text="Browse", command=pick_in).grid(row=0, column=2)
    tk.Label(frm, text="Output:").grid(row=1, column=0, sticky="w")
    tk.Entry(frm, textvariable=var_out, width=40).grid(row=1, column=1, padx=6)
    tk.Button(frm, text="Browse", command=pick_out).grid(row=1, column=2)

    # options
    opt=tk.Frame(root)
    opt.pack(pady=4)
    var_block=tk.StringVar(value="65536")
    var_dict=tk.BooleanVar(value=False)
    tk.Label(opt, text="Block:").pack(side="left")
    ttk = __import__("tkinter.ttk", fromlist=["Combobox"])
    cb=ttk.Combobox(opt, textvariable=var_block, values=["4096","16384","65536","131072"], width=10, state="readonly")
    cb.pack(side="left", padx=6)
    tk.Checkbutton(opt, text="Shared Dict (1MB→64KB)", variable=var_dict).pack(side="left", padx=6)

    # log
    log=tk.Text(root, height=10, font=("Consolas", 9))
    log.pack(fill="both", expand=True, padx=16, pady=8)
    # log every GUI line to file too (bug reports need the full story)
    lg = get_logger()
    def glog(msg):
        try:
            lg.info(msg)
        except Exception:
            pass
        log.insert("end", msg + "\n")
    def do_comp():
        try:
            inp=var_in.get(); out=var_out.get()
            if not inp or not out:
                messagebox.showwarning("rissa", "Pick input and output")
                return
            glog(f"GUI compress in={inp} out={out} block={var_block.get()} dict={var_dict.get()}")
            data=pathlib.Path(inp).read_bytes()
            ent=shannon_entropy(data)
            t0=time.perf_counter()
            comp, hist, d = compress_with_dict(data, block_size=int(var_block.get()), use_dict=var_dict.get())
            t=time.perf_counter()-t0
            pathlib.Path(out).write_bytes(comp)
            glog(f"Compress {len(data)} -> {len(comp)} {len(comp)/len(data)*100:.1f}% {len(comp)*8/len(data):.2f} b/sym ent {ent:.2f} {t:.2f}s hist {dict(hist.most_common(3))}")
            log.see("end")
        except Exception as e:
            glog(f"ERROR compress: {type(e).__name__}: {e}")
            messagebox.showerror("rissa", f"{e}\n\n{report_bug(f'GUI compress: {e}')}")
    def do_decomp():
        try:
            inp=var_in.get(); out=var_out.get()
            data=pathlib.Path(inp).read_bytes()
            dec=decompress_with_dict(data)
            pathlib.Path(out).write_bytes(dec)
            glog(f"Decompress {len(data)} -> {len(dec)} -> {out}")
            log.see("end")
        except Exception as e:
            glog(f"ERROR decompress: {type(e).__name__}: {e}")
            messagebox.showerror("rissa", f"{e}\n\n{report_bug(f'GUI decompress: {e}')}")

    def do_copy_log():
        try:
            root.clipboard_clear()
            root.clipboard_append(log.get("1.0", "end"))
            messagebox.showinfo("rissa", f"Log copied.\nPaste it on Discord:\n{DISCORD_URL}\n\nFull file: {log_path()}")
        except Exception as e:
            messagebox.showerror("rissa", str(e))

    btns=tk.Frame(root)
    btns.pack(pady=6)
    tk.Button(btns, text="Compress", bg="#0f172a", fg="white", padx=16, command=do_comp).pack(side="left", padx=6)
    tk.Button(btns, text="Decompress", padx=16, command=do_decomp).pack(side="left", padx=6)
    tk.Button(btns, text="Copy log", padx=16, command=do_copy_log).pack(side="left", padx=6)
    tk.Button(btns, text="Discord", padx=16, command=lambda: __import__("webbrowser").open(DISCORD_URL)).pack(side="left", padx=6)
    tk.Button(btns, text="Open rissa.web.app", command=lambda: __import__("webbrowser").open("https://rissa.web.app")).pack(side="left", padx=6)

    # drag-drop hint
    tk.Label(root, text="Tip: pip install rissa-compress  •  rissa input.bin -o out.rissa", fg="#64748b", font=("Segoe UI", 8)).pack(pady=4)
    root.mainloop()

if __name__=="__main__":
    ap=argparse.ArgumentParser(prog="rissa_tool", description="rissa tool - https://rissa.web.app")
    sub=ap.add_subparsers(dest="cmd")
    c=sub.add_parser("compress", help="compress")
    c.add_argument("input"); c.add_argument("-o","--output", required=True); c.add_argument("--block", type=int, default=65536); c.add_argument("--dict", action="store_true", dest="use_dict"); c.add_argument("--fast", action="store_true", help="two-stage MDL screen, skip BWT family (~10x faster)")
    d=sub.add_parser("decompress", help="decompress")
    d.add_argument("input"); d.add_argument("-o","--output", required=True)
    g=sub.add_parser("gui", help="launch GUI")
    sub.add_parser("doctor", help="report C extensions + backends (no silent fallback)")
    sub.add_parser("logs", help="show log file location for bug reports")
    args=ap.parse_args()
    get_logger().info(f"cmd={args.cmd} argv={sys.argv[1:]}")
    try:
        if args.cmd=="compress":
            cli_compress(args.input, args.output, args.block, args.use_dict, fast=args.fast)
        elif args.cmd=="decompress":
            cli_decompress(args.input, args.output)
        elif args.cmd=="doctor":
            cli_doctor()
        elif args.cmd=="logs":
            print(f"logs: {log_path()}")
            print(f"bugs: paste the log on Discord: {DISCORD_URL}")
        elif args.cmd=="gui" or args.cmd is None:
            launch_gui()
        else:
            ap.print_help()
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        print(report_bug(f"CLI {args.cmd}: {e}"), file=sys.stderr)
        sys.exit(1)
