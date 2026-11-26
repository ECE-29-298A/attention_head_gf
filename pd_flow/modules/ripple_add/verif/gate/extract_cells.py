#!/usr/bin/env python3
"""Build a self-contained gate-level DUT file: netlist + the cell models it uses.

Usage: extract_cells.py <netlist.v> <cell_model_dir> <out.v>

The GF180 cell library (gf180mcu_fd_sc_mcu7t5v0.v + primitives.v) is not parseable as a
whole by Yosys (unnamed UDP instances) or Verilator (strength on the hold cell), so only the
modules and UDPs the netlist instantiates (transitively) are copied. The library is
preprocessed with Verilator -E and these defines:
  FUNCTIONAL       defined: drops specify blocks and timing-check/notifier code
  USE_POWER_PINS   not defined: Yosys netlists have no power pins
The netlist itself is copied unchanged. Prints the cells used.
"""
import os
import re
import subprocess
import sys

KW = {"module", "endmodule", "input", "output", "inout", "wire", "reg", "assign", "and",
      "or", "not", "nand", "nor", "xor", "xnor", "buf", "bufif0", "bufif1", "notif0",
      "notif1", "pullup", "pulldown", "supply0", "supply1", "always", "initial", "begin",
      "end", "if", "else", "specify", "endspecify", "primitive", "endprimitive", "table",
      "endtable", "integer", "parameter", "localparam", "genvar", "generate", "endgenerate"}


def preprocess(path):
    p = subprocess.run(["verilator", "-E", "-P", "-DFUNCTIONAL", path], capture_output=True, text=True)
    if p.returncode:
        sys.exit(f"verilator -E failed on {path}:\n{p.stderr[-2000:]}")
    return p.stdout


def blocks(text, start, end):
    out = {}
    for m in re.finditer(rf"\b{start}\s+([A-Za-z_][\w$]*)\b.*?\b{end}\b", text, re.S):
        out[m.group(1)] = m.group(0)
    return out


def instantiated(body):
    # "<type> [#(...)] <inst> (" or "<type> (" (unnamed primitive/UDP instance)
    names = set()
    for m in re.finditer(r"^\s*([A-Za-z_][\w$]*)\s+(?:#\s*\(.*?\)\s*)?(?:\([^;]*?\)\s*)?([A-Za-z_][\w$]*\s*)?\(", body, re.M):
        if m.group(1) not in KW:
            names.add(m.group(1))
    return names


def main():
    netlist, cdir, out = sys.argv[1:4]
    mods = blocks(preprocess(os.path.join(cdir, "gf180mcu_fd_sc_mcu7t5v0.v")), "module", "endmodule")
    prims = blocks(preprocess(os.path.join(cdir, "primitives.v")), "primitive", "endprimitive")
    net = open(netlist).read()
    netmods = blocks(net, "module", "endmodule")
    todo = set().union(*(instantiated(b) for b in netmods.values())) - set(netmods)
    used, missing = [], []
    while todo:
        n = todo.pop()
        if n in used:
            continue
        if n in mods:
            used.append(n)
            todo |= instantiated(mods[n]) - set(used)
        elif n in prims:
            used.append(n)
        else:
            missing.append(n)
    if missing:
        sys.exit(f"cells not found in the library: {sorted(missing)}")
    with open(out, "w") as f:
        f.write(f"// gate-level DUT: {os.path.basename(netlist)} (unchanged) + {len(used)} cell models\n")
        f.write(f"// from {cdir} (preprocessed: FUNCTIONAL defined, USE_POWER_PINS undefined)\n")
        f.write(net.rstrip() + "\n\n")
        for n in sorted(used):
            f.write((mods.get(n) or prims[n]) + "\n\n")
    top_cells = sorted(set().union(*(instantiated(b) for b in netmods.values())) - set(netmods))
    print(f"RESULT cells netlist_modules={sorted(netmods)} cell_types={len(top_cells)} "
          f"models_copied={len(used)} udps={sum(n in prims for n in used)}")
    print("cells:", " ".join(top_cells))


if __name__ == "__main__":
    main()
