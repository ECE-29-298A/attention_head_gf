#!/usr/bin/env python3
"""Agent 2: gate-level mutants of divider on the GF180-mapped golden netlist golden_00.v (chip
configuration LATCH_DENOMINATOR=0, CHECK_INVALID=0; gate_synth.sh = copy of verif/gate/synth_gf180.sh,
byte-identical output to verif/gate/netlists/divider_00_gf180.v).
g*: hand edits, each checked to match exactly once (or 'ALL').  s*: mapped netlists of RTL mutants.
Writes gate_mutants/<name>.v (first line "// gate mutant <name>: ...") and gate_mutants/MANIFEST.json."""
import json, os, re, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
GM = os.path.join(HERE, "gate_mutants")
N0 = open(os.path.join(HERE, "gate_netlists", "golden_00.v")).read()
C = "gf180mcu_fd_sc_mcu7t5v0__"
G = []
def g(name, cls, desc, *pairs): G.append((name, cls, desc, list(pairs)))

g("g01_dswap_result3_4", "functional-bug", "D inputs of flops result[3] (_611_) and result[4] (_612_) swapped",
  ("    .D(_008_),\n    .Q(result[3])", "    .D(_007_),\n    .Q(result[3])"),
  ("    .D(_007_),\n    .Q(result[4])", "    .D(_008_),\n    .Q(result[4])"))
g("g02_xor_to_xnor_407", "functional-bug", "datapath cell _407_ xor2_1 replaced by xnor2_1",
  (f"{C}xor2_1 _407_ (\n    .A1(_130_),\n    .A2(_131_),\n    .Z(_223_)", f"{C}xnor2_1 _407_ (\n    .A1(_130_),\n    .A2(_131_),\n    .ZN(_223_)"))
g("g03_buf_result11", "equivalent", "a buf_1 inserted on the result[11] flop output (models resizer buffering)",
  ("    .Q(result[11])\n", "    .Q(r11_pre)\n"),
  ("  assign quotient[21:0]", f"  {C}buf_1 rsz_buf (\n    .I(r11_pre),\n    .Z(result[11])\n  );\n  assign quotient[21:0]"),
  ("  input clk;\n", "  input clk;\n  wire r11_pre;\n"))
g("g04_clkbuf", "equivalent", "all flops clocked through one clkbuf_1 from clk (models a post-CTS netlist)",
  ("    .CLK(clk),", "    .CLK(clk_buf),", "ALL"),
  ("  assign quotient[21:0]", f"  {C}clkbuf_1 cts_buf (\n    .I(clk),\n    .Z(clk_buf)\n  );\n  assign quotient[21:0]"),
  ("  input clk;\n", "  input clk;\n  wire clk_buf;\n"))
g("g05_dffnq_done", "structural", "done flop _620_ replaced by negative-edge dffnq_1",
  (f"  {C}dffq_1 _620_ (\n    .CLK(clk),", f"  {C}dffnq_1 _620_ (\n    .CLKN(clk),"))
g("g06_busy_stuck0", "out-of-context-bug", "busy output inverter input tied high (busy stuck at 0; the chip leaves busy unused)",
  ("    .I(_062_),\n    .ZN(busy)", "    .I(1'b1),\n    .ZN(busy)"))

S = [("m03_ties_toward_zero", "functional-bug"), ("m05_neg_off_by_one", "functional-bug"),
     ("m16_rare_point", "functional-bug"), ("m17_rare_maxL", "functional-bug"),
     ("m23_carry_bit8_lost", "functional-bug"), ("m01_latency_plus1", "functional-bug"),
     ("e02_negate_form", "equivalent"), ("e03_compare_form", "equivalent")]

def main():
    os.makedirs(GM, exist_ok=True)
    man = {}
    for name, cls, desc, pairs in G:
        t = N0
        for p in pairs:
            if len(p) == 3:
                assert t.count(p[0]) >= 2, name; t = t.replace(p[0], p[1])
            else:
                assert t.count(p[0]) == 1, f"{name}: {t.count(p[0])} matches for {p[0][:50]!r}"; t = t.replace(p[0], p[1])
        assert t != N0
        open(os.path.join(GM, name + ".v"), "w").write(f"// gate mutant {name}: {desc}\n" + t)
        man[name] = {"class": cls, "config": "00", "description": desc}
    mm = json.load(open(os.path.join(HERE, "mutants", "MANIFEST.json")))
    for rtl, cls in S:
        out = os.path.join(GM, f"s_{rtl}.v")
        subprocess.run([os.path.join(HERE, "gate_synth.sh"), out, "00", os.path.join(HERE, "mutants", rtl + ".v")], check=True)
        desc = f"mapped GF180 netlist (config 00) of RTL mutant {rtl} ({mm[rtl]['description']})"
        body = open(out).read()
        open(out, "w").write(f"// gate mutant s_{rtl}: {desc}\n" + body)
        man[f"s_{rtl}"] = {"class": cls, "config": "00", "description": desc}
    json.dump(man, open(os.path.join(GM, "MANIFEST.json"), "w"), indent=1)
    print(len(man), "gate mutants")

if __name__ == "__main__":
    main()
