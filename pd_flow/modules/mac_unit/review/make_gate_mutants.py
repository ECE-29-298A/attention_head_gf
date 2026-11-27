#!/usr/bin/env python3
"""Agent 2: gate-level mutants of mac_unit on the GF180-mapped golden netlist gate_netlists/golden.v
(gate_synth.sh). g*: hand edits, each checked to match exactly once (or 'ALL').
s*: mapped netlists of RTL mutants. Writes gate_mutants/<name>.v + MANIFEST.json."""
import json, os, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
GM = os.path.join(HERE, "gate_mutants")
N0 = open(os.path.join(HERE, "gate_netlists", "golden.v")).read()
C = "gf180mcu_fd_sc_mcu7t5v0__"
G = []
def g(name, cls, desc, *pairs): G.append((name, cls, desc, list(pairs)))
g("g01_ring_dswap", "functional-bug", "D inputs of ring head flops O0[0] (_835_) and O0[1] (_836_) swapped",
  ("    .D(ring[20]),\n    .Q(O0[0])", "    .D(ring[21]),\n    .Q(O0[0])"),
  ("    .D(ring[21]),\n    .Q(O0[1])", "    .D(ring[20]),\n    .Q(O0[1])"))
g("g02_xor_to_xnor_405", "functional-bug", "datapath cell _405_ xor2_1 replaced by xnor2_1",
  (f"{C}xor2_1 _405_ (\n    .A1(_119_),\n    .A2(_124_),\n    .Z(_144_)", f"{C}xnor2_1 _405_ (\n    .A1(_119_),\n    .A2(_124_),\n    .ZN(_144_)"))
g("g03_L5_stuck0", "functional-bug", "L[5] flop D tied to 0",
  ("    .D(_027_),\n    .Q(L[5])", "    .D(1'b0),\n    .Q(L[5])"))
g("g04_buf_O0_0", "equivalent", "buf_1 inserted on the O0[0] flop output (models resizer buffering)",
  ("    .Q(O0[0])\n", "    .Q(o0_pre)\n"),
  ("  assign _000_[139:0]", f"  {C}buf_1 rsz_buf (\n    .I(o0_pre),\n    .Z(O0[0])\n  );\n  assign _000_[139:0]"),
  ("  input clk;\n", "  input clk;\n  wire o0_pre;\n"))
g("g05_clkbuf", "equivalent", "all flops clocked through one clkbuf_1 (models a post-CTS netlist)",
  ("    .CLK(clk),", "    .CLK(clk_buf),", "ALL"),
  ("  assign _000_[139:0]", f"  {C}clkbuf_1 cts_buf (\n    .I(clk),\n    .Z(clk_buf)\n  );\n  assign _000_[139:0]"),
  ("  input clk;\n", "  input clk;\n  wire clk_buf;\n"))
g("g06_dffn_S3", "functional-bug", "S[3] flop replaced by a negative-edge dffnq_1",
  (f"  {C}dffq_1 _817_ (\n    .CLK(clk),", f"  {C}dffnq_1 _817_ (\n    .CLKN(clk),"))
S = [("m07_first_load_no_accum_en", "functional-bug"), ("m14_rare_W_A5_b3", "functional-bug"),
     ("m21_bit_on_no_accum_en", "functional-bug"), ("m15_rare_qi_80", "functional-bug"),
     ("e01_plus_adder", "equivalent")]
def main():
    os.makedirs(GM, exist_ok=True); man = {}
    for name, cls, desc, pairs in G:
        t = N0
        for p in pairs:
            if len(p) == 3:
                assert t.count(p[0]) >= 2, name; t = t.replace(p[0], p[1])
            else:
                assert t.count(p[0]) == 1, f"{name}: {t.count(p[0])} matches for {p[0][:50]!r}"; t = t.replace(p[0], p[1])
        assert t != N0
        open(os.path.join(GM, name + ".v"), "w").write(f"// gate mutant {name}: {desc}\n" + t)
        man[name] = {"class": cls, "description": desc}
    mm = json.load(open(os.path.join(HERE, "mutants", "MANIFEST.json")))
    for rtl, cls in S:
        out = os.path.join(GM, f"s_{rtl}.v")
        subprocess.run([os.path.join(HERE, "gate_synth.sh"), out, os.path.join(HERE, "mutants", rtl + ".v")], check=True)
        desc = f"mapped GF180 netlist of RTL mutant {rtl} ({mm[rtl]['description']})"
        body = open(out).read(); open(out, "w").write(f"// gate mutant s_{rtl}: {desc}\n" + body)
        man[f"s_{rtl}"] = {"class": cls, "description": desc}
    json.dump(man, open(os.path.join(GM, "MANIFEST.json"), "w"), indent=1)
    print(len(man), "gate mutants")
if __name__ == "__main__":
    main()
