#!/usr/bin/env python3
"""Agent 2: gate-level mutants of exp_lut on the GF180-mapped golden netlists.

g*: hand edits of gate_netlists/golden_R0.v (chip configuration) or golden_R1.v (block test),
    each one checked edit.
s*: mapped netlists of selected RTL mutants (gate_synth.sh, same recipe as max_reg's
    synth_gf180.sh), built by this script.
Writes gate_mutants/<name>.v (first line "// gate mutant <name>: ...") and gate_mutants/MANIFEST.json
with class and the REGISTERED value of the netlist.
"""
import json
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
GM = os.path.join(HERE, "gate_mutants")
R0 = open(os.path.join(HERE, "gate_netlists", "golden_R0.v")).read()
R1 = open(os.path.join(HERE, "gate_netlists", "golden_R1.v")).read()
C = "gf180mcu_fd_sc_mcu7t5v0__"
G = []


def g(name, cls, reg, desc, base, *pairs):
    G.append((name, cls, reg, desc, base, list(pairs)))


g("g01_nand2_to_nor2_W3", "functional-bug", 0, "R0: cell _097_ (drives W[3]) nand2_1 replaced by nor2_1", R0,
  (f"{C}nand2_1 _097_ (", f"{C}nor2_1 _097_ ("))
g("g02_swap_W0_W1", "functional-bug", 0, "R0: output nets W[0] and W[1] swapped", R0,
  ("    .Z(W[1])\n", "    .Z(W[@0])\n"), ("    .ZN(W[0])\n", "    .ZN(W[1])\n"), ("W[@0]", "W[0]"))
g("g03_tie_input", "equivalent", 0, "R0: input A2 of cell _139_ tied to 1'b1 (found redundant: exhaustive sweep 0 mismatches; EQY to confirm)", R0,
  ("  gf180mcu_fd_sc_mcu7t5v0__nand2_1 _139_ (\n    .A1(_074_),\n    .A2(_076_),",
   "  gf180mcu_fd_sc_mcu7t5v0__nand2_1 _139_ (\n    .A1(_074_),\n    .A2(1'b1),"))
g("g09_stuck_W3_in", "functional-bug", 0, "R0: input A1 of cell _097_ (drives W[3]) tied to 1'b1 (stuck-at-1)", R0,
  ("  gf180mcu_fd_sc_mcu7t5v0__nand2_1 _097_ (\n    .A1(_027_),", "  gf180mcu_fd_sc_mcu7t5v0__nand2_1 _097_ (\n    .A1(1'b1),"))
g("g04_buf_internal", "equivalent", 0, "R0: a buf_1 inserted on the W[3] output (equivalent; models resizer buffering)", R0,
  ("    .ZN(W[3])\n", "    .ZN(w3_pre)\n"),
  ("  assign done = start;", f"  {C}buf_1 rsz_buf (\n    .I(w3_pre),\n    .Z(W[3])\n  );\n  assign done = start;"),
  ("  wire [7:0] W;\n", "  wire [7:0] W;\n  wire w3_pre;\n"))
g("g05_dffnq_W0", "structural", 1, "R1: flop W[0] replaced by negative-edge dffnq_1", R1,
  (f"  {C}dffq_1 _208_ (\n    .CLK(clk),", f"  {C}dffnq_1 _208_ (\n    .CLKN(clk),"))
g("g06_clkbuf", "equivalent", 1, "R1: all 9 flops clocked through one clkbuf_1 from clk (equivalent; models a post-CTS netlist)", R1,
  ("    .CLK(clk),", "    .CLK(clk_buf),", "ALL"),
  ("endmodule", f"  {C}clkbuf_1 cts_buf (\n    .I(clk),\n    .Z(clk_buf)\n  );\nendmodule"),
  ("  wire [7:0] W;\n", "  wire [7:0] W;\n  wire clk_buf;\n"))
g("g07_dswap_W6_W7", "functional-bug", 1, "R1: D inputs of flops W[6] and W[7] swapped", R1)
g("g08_latq_done", "structural", 1, "R1: done flop replaced by latch latq_1 (E = clk, transparent high)", R1,
  (f"  {C}dffq_1 _216_ (\n    .CLK(clk),", f"  {C}latq_1 _216_ (\n    .E(clk),"))


def dswap(text):
    # swap the D nets of the flops whose Q are W[6] and W[7]
    m6 = re.search(r"\.D\((\w+)\),\n    \.Q\(W\[6\]\)", text)
    m7 = re.search(r"\.D\((\w+)\),\n    \.Q\(W\[7\]\)", text)
    a, b = m6.group(1), m7.group(1)
    text = text.replace(f".D({a}),\n    .Q(W[6])", f".D(@@),\n    .Q(W[6])")
    text = text.replace(f".D({b}),\n    .Q(W[7])", f".D({a}),\n    .Q(W[7])")
    return text.replace("@@", b)


S = [  # mapped RTL mutants: (rtl mutant, REGISTERED, class)
    ("m01_lut8_34", 0, "functional-bug"),
    ("m13_carry_lost", 0, "functional-bug"),
    ("m14_bit21_ignored", 0, "out-of-context-bug"),
    ("m19_rare_point", 0, "functional-bug"),
    ("m30_r0_rst_gates_W", 0, "out-of-context-bug"),
    ("e02_fullwidth_round", 0, "equivalent"),
    ("m21_r1_latency2", 1, "functional-bug"),
    ("m23_r1_load_always", 1, "functional-bug"),
    ("m25_r1_start_over_reset", 1, "functional-bug"),
    ("e04_r1_mux_hold", 1, "equivalent"),
]


def main():
    os.makedirs(GM, exist_ok=True)
    man = {}
    for name, cls, reg, desc, base, pairs in G:
        t = base
        if name == "g07_dswap_W6_W7":
            t = dswap(t)
        for p in pairs:
            old, new = p[0], p[1]
            if len(p) == 3:
                assert t.count(old) >= 2, name
                t = t.replace(old, new)
            else:
                assert t.count(old) == 1, f"{name}: {t.count(old)} matches for {old[:50]!r}"
                t = t.replace(old, new)
        assert t != base
        open(os.path.join(GM, name + ".v"), "w").write(f"// gate mutant {name}: {desc}\n" + t)
        man[name] = {"class": cls, "registered": reg, "description": desc}
    mm = json.load(open(os.path.join(HERE, "mutants", "MANIFEST.json")))
    for rtl, reg, cls in S:
        out = os.path.join(GM, f"s_{rtl}.v")
        subprocess.run([os.path.join(HERE, "gate_synth.sh"), out, os.path.join(HERE, "mutants", rtl + ".v"), str(reg)], check=True)
        desc = f"mapped GF180 netlist (REGISTERED={reg}) of RTL mutant {rtl} ({mm[rtl]['description']})"
        body = open(out).read()
        open(out, "w").write(f"// gate mutant s_{rtl}: {desc}\n" + body)
        man[f"s_{rtl}"] = {"class": cls, "registered": reg, "description": desc}
    json.dump(man, open(os.path.join(GM, "MANIFEST.json"), "w"), indent=1)
    print(len(man), "gate mutants")


if __name__ == "__main__":
    main()
