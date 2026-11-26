#!/usr/bin/env python3
"""Build self-contained gate-level DUT files for max_reg: netlist + the cell models it uses.

Usage: extract_cells.py <netlist.v> <cell_model_dir> <liberty.lib> <out_sim.v> <out_yosys.v>

Derived from pd_flow/modules/ripple_add/verif/gate/extract_cells.py, with two changes:
  1. Unnamed UDP instances written without a space before "(" (as in the GF180 flop
     models, "gf180mcu_fd_sc_mcu7t5v0__udp_n_iq_ff( IQ1, ...") are now found, so a
     flop cell pulls in its UDP. (The ripple_add version missed them; it never needed them.)
  2. Two views are written, because Yosys cannot read UDPs (`primitive ... table`):
     - out_sim.v   netlist + every needed Verilog model + UDPs. Used by Verilator (which
                   supports UDP tables) and Icarus (4-state, full UDP semantics).
     - out_yosys.v netlist + the Verilog models of the cells that need no UDP (the
                   combinational cells) + Yosys `read_liberty -ignore_miss_func` models of
                   the cells that do (the flops), taken from the cell's `ff` group in the
                   PDK liberty and written back with `write_verilog -noattr`. Used by the
                   Yosys structure check and SymbiYosys.
   So the flop behaviour in simulation comes from the PDK Verilog UDP and in formal from
   the PDK liberty: two independent PDK views, cross-checked by running both.
The Verilog library is preprocessed with Verilator -E and these defines:
  FUNCTIONAL       defined: drops specify blocks and timing-check/notifier code
  USE_POWER_PINS   not defined: Yosys netlists have no power pins
The netlist itself is copied unchanged into both views, followed by the marker line END
(lint/check_lint.py treats warnings after it as PDK-model warnings). Prints the cells used.
"""
import os
import re
import subprocess
import sys
import tempfile

KW = {"module", "endmodule", "input", "output", "inout", "wire", "reg", "assign", "and",
      "or", "not", "nand", "nor", "xor", "xnor", "buf", "bufif0", "bufif1", "notif0",
      "notif1", "pullup", "pulldown", "supply0", "supply1", "always", "initial", "begin",
      "end", "if", "else", "specify", "endspecify", "primitive", "endprimitive", "table",
      "endtable", "integer", "parameter", "localparam", "genvar", "generate", "endgenerate",
      "case", "endcase", "default", "posedge", "negedge", "or", "tri", "time", "real"}


END = "// ==== end of netlist; PDK cell models follow ===="  # lint/check_lint.py looks for this


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
    # "<type> [#(...)] <inst> (", or "<type>(" / "<type> (" for an unnamed primitive/UDP
    names = set()
    for m in re.finditer(r"^\s*([A-Za-z_][\w$]*)\s*(?:#\s*\(.*?\)\s*)?(?:\([^;]*?\)\s*)?([A-Za-z_][\w$]*\s*)?\(",
                         body, re.M):
        if m.group(1) not in KW:
            names.add(m.group(1))
    return names


def liberty_models(lib, cells):
    """Yosys functional models of `cells` from the liberty file, as Verilog text."""
    with tempfile.TemporaryDirectory() as t:
        out = os.path.join(t, "lib_cells.v")
        sel = " ".join(cells)
        p = subprocess.run(["yosys", "-q", "-p",
                            f"read_liberty -ignore_miss_func {lib}; select -none; "
                            f"select {sel}; write_verilog -noattr -selected {out}"],
                           capture_output=True, text=True)
        if p.returncode or not os.path.exists(out):
            sys.exit(f"yosys read_liberty failed:\n{p.stdout[-2000:]}{p.stderr[-2000:]}")
        text = open(out).read()
    got = blocks(text, "module", "endmodule")
    missing = [c for c in cells if c not in got]
    if missing:
        sys.exit(f"liberty has no functional model for {missing}")
    return got


def main():
    netlist, cdir, lib, out_sim, out_ys = sys.argv[1:6]
    mods = blocks(preprocess(os.path.join(cdir, "gf180mcu_fd_sc_mcu7t5v0.v")), "module", "endmodule")
    prims = blocks(preprocess(os.path.join(cdir, "primitives.v")), "primitive", "endprimitive")
    net = open(netlist).read()
    netmods = blocks(net, "module", "endmodule")
    if not netmods:
        sys.exit(f"no module found in {netlist}")
    top_cells = sorted(set().union(*(instantiated(b) for b in netmods.values())) - set(netmods))

    def closure(name):
        seen, todo = [], {name}
        while todo:
            n = todo.pop()
            if n in seen:
                continue
            if n in mods:
                seen.append(n)
                todo |= instantiated(mods[n]) - set(seen)
            elif n in prims:
                seen.append(n)
            else:
                sys.exit(f"cell or primitive not found in the library: {n} (needed by {name})")
        return seen

    used, seq = [], []
    for c in top_cells:
        cl = closure(c)
        used += [n for n in cl if n not in used]
        if any(n in prims for n in cl):
            seq.append(c)
    hdr = f"// gate-level DUT: {os.path.basename(netlist)} (unchanged) + cell models from {cdir}\n" \
          f"// (Verilog preprocessed: FUNCTIONAL defined, USE_POWER_PINS undefined)\n"
    with open(out_sim, "w") as f:
        f.write(hdr + f"// simulation view: {len(used)} Verilog models / UDPs\n")
        f.write(net.rstrip() + "\n" + END + "\n\n")
        for n in sorted(used):
            f.write((mods.get(n) or prims[n]) + "\n\n")
    libm = liberty_models(lib, seq) if seq else {}
    comb_used = []
    for c in top_cells:
        if c not in seq:
            comb_used += [n for n in closure(c) if n not in comb_used]
    with open(out_ys, "w") as f:
        f.write(hdr + f"// Yosys view: {len(comb_used)} Verilog models; flop cells {seq} from the liberty\n"
                      f"// {lib} (read_liberty -ignore_miss_func)\n")
        f.write(net.rstrip() + "\n" + END + "\n\n")
        for n in sorted(comb_used):
            f.write(mods[n] + "\n\n")
        for c in seq:
            f.write(libm[c] + "\n\n")
    nl_lines = net.rstrip().count("\n") + 1
    print(f"RESULT cells netlist_modules={sorted(netmods)} cell_types={len(top_cells)} "
          f"models_copied={len(used)} udps={sum(n in prims for n in used)} "
          f"liberty_flop_cells={len(seq)} netlist_lines={nl_lines}")
    print("cells:", " ".join(top_cells))
    print("liberty-modelled (sequential):", " ".join(seq) or "none")


if __name__ == "__main__":
    main()
