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
import argparse, sys, pathlib, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "deep_compress"))

from deep_compress.compressor_v3 import compress_with_dict, decompress_with_dict
from deep_compress.rans import shannon_entropy

def cli_compress(inp, out, block, use_dict, backend="zstd"):
    data = pathlib.Path(inp).read_bytes()
    ent = shannon_entropy(data) if data else 0
    t0=time.perf_counter()
    comp, hist, d = compress_with_dict(data, backend=backend, block_size=block, use_dict=use_dict)
    t=time.perf_counter()-t0
    pathlib.Path(out).write_bytes(comp)
    bits = len(comp)*8/len(data) if data else 0
    print(f"rissa compress: {len(data)} -> {len(comp)} {len(comp)/len(data)*100:.1f}% {bits:.2f} b/sym ent {ent:.2f} time {t:.2f}s hist {dict(hist.most_common(3))} dict {len(d) if d else 0} -> {out}")

def cli_decompress(inp, out):
    data = pathlib.Path(inp).read_bytes()
    t0=time.perf_counter()
    dec = decompress_with_dict(data)
    t=time.perf_counter()-t0
    pathlib.Path(out).write_bytes(dec)
    print(f"rissa decompress: {len(data)} -> {len(dec)} time {t:.2f}s -> {out}")

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
    def do_comp():
        try:
            inp=var_in.get(); out=var_out.get()
            if not inp or not out:
                messagebox.showwarning("rissa", "Pick input and output")
                return
            data=pathlib.Path(inp).read_bytes()
            ent=shannon_entropy(data)
            t0=time.perf_counter()
            comp, hist, d = compress_with_dict(data, block_size=int(var_block.get()), use_dict=var_dict.get())
            t=time.perf_counter()-t0
            pathlib.Path(out).write_bytes(comp)
            log.insert("end", f"Compress {len(data)} -> {len(comp)} {len(comp)/len(data)*100:.1f}% {len(comp)*8/len(data):.2f} b/sym ent {ent:.2f} {t:.2f}s hist {dict(hist.most_common(3))}\n")
            log.see("end")
        except Exception as e:
            messagebox.showerror("rissa", str(e))
    def do_decomp():
        try:
            inp=var_in.get(); out=var_out.get()
            data=pathlib.Path(inp).read_bytes()
            dec=decompress_with_dict(data)
            pathlib.Path(out).write_bytes(dec)
            log.insert("end", f"Decompress {len(data)} -> {len(dec)} -> {out}\n")
            log.see("end")
        except Exception as e:
            messagebox.showerror("rissa", str(e))

    btns=tk.Frame(root)
    btns.pack(pady=6)
    tk.Button(btns, text="Compress", bg="#0f172a", fg="white", padx=16, command=do_comp).pack(side="left", padx=6)
    tk.Button(btns, text="Decompress", padx=16, command=do_decomp).pack(side="left", padx=6)
    tk.Button(btns, text="Open rissa.web.app", command=lambda: __import__("webbrowser").open("https://rissa.web.app")).pack(side="left", padx=6)

    # drag-drop hint
    tk.Label(root, text="Tip: pip install rissa-compress  •  rissa input.bin -o out.rissa", fg="#64748b", font=("Segoe UI", 8)).pack(pady=4)
    root.mainloop()

if __name__=="__main__":
    ap=argparse.ArgumentParser(prog="rissa_tool", description="rissa tool - https://rissa.web.app")
    sub=ap.add_subparsers(dest="cmd")
    c=sub.add_parser("compress", help="compress")
    c.add_argument("input"); c.add_argument("-o","--output", required=True); c.add_argument("--block", type=int, default=65536); c.add_argument("--dict", action="store_true", dest="use_dict")
    d=sub.add_parser("decompress", help="decompress")
    d.add_argument("input"); d.add_argument("-o","--output", required=True)
    g=sub.add_parser("gui", help="launch GUI")
    args=ap.parse_args()
    if args.cmd=="compress":
        cli_compress(args.input, args.output, args.block, args.use_dict)
    elif args.cmd=="decompress":
        cli_decompress(args.input, args.output)
    elif args.cmd=="gui" or args.cmd is None:
        launch_gui()
    else:
        ap.print_help()
