#!/usr/bin/env python3
"""Agent 2: RTL mutants of mac_unit (golden = review/golden_copy/mac_unit.v, copy of snapshot/).
Each mutant is one or more checked text edits (each old string must match exactly once).
Writes mutants/<name>.v (first line "// mutant <name>: <description>") and mutants/MANIFEST.json.
Classes: functional-bug (wrong in the chip, OUTPUTS=8, controller-driven),
         out-of-context-bug (wrong only for port inputs the controller never drives, e.g.
                             accum_en with !accum_mode, score_en with accum_mode),
         power-up (adds reset/init; must be killed),
         equivalent (expected survivor)."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
G = open(os.path.join(HERE, "golden_copy", "mac_unit.v")).read()
M = []
def m(name, cls, desc, *pairs): M.append((name, cls, desc, pairs))

m("m01_accum_bit7_positive", "functional-bug", "accumulate: bit 7 of v adds +128*W instead of -128*W (v treated unsigned)",
  ("wire neg = accum_mode ? (accum_en && top)", "wire neg = accum_mode ? 1'b0"))
m("m02_score_ignore_subtract", "functional-bug", "score: subtract ignored (pass 2 adds instead of M - S)",
  ("(top ^ subtract)", "top"))
m("m03_score_bit7_positive", "functional-bug", "score: ki bit 7 has weight +128 (ki treated unsigned)",
  ("(top ^ subtract)", "subtract"))
m("m04_W_sign_extended", "functional-bug", "accumulate: W sign-extended (wrong only for W >= 128)",
  ("{1'b0, W}", "{W[7], W}"))
m("m05_qi_zero_extended", "functional-bug", "score: qi zero-extended (wrong for negative qi)",
  ("{qi[7], qi}", "{1'b0, qi}"))
m("m06_first_load_every_bit", "functional-bug", "first load ignores top: token 0 restarts from 0 at every bit",
  ("wire load_o = accum_en && first && top;", "wire load_o = accum_en && first;"))
m("m07_first_load_no_accum_en", "functional-bug", "first load ignores accum_en: head cleared whenever first && bit_sel==7 (e.g. DIV states with last = 0)",
  ("wire load_o = accum_en && first && top;", "wire load_o = first && top;"))
m("m08_ring_no_bypass", "functional-bug", "ring tail always takes sum[19:0] (no bypass while scoring)",
  ("ring <= {accum_mode ? sum[19:0] : O0,", "ring <= {sum[19:0],"))
m("m09_bypass_by_accum_en", "out-of-context-bug", "ring update selected by accum_en instead of accum_mode (differs only for accum_en && !accum_mode)",
  ("ring <= {accum_mode ? sum[19:0] : O0,", "ring <= {accum_en ? sum[19:0] : O0,"))
m("m10_L_every_component", "functional-bug", "L condition drops sel == 0 (adds W for every component)",
  ("if (accum_en && ~|sel && bit_sel == 3'd0)", "if (accum_en && bit_sel == 3'd0)"))
m("m11_L_at_bit7", "out-of-context-bug", "L updates at bit_sel == 7 instead of 0 (same W within a V block in the chip; differs at the port)",
  ("if (accum_en && ~|sel && bit_sel == 3'd0)", "if (accum_en && ~|sel && bit_sel == 3'd7)"))
m("m12_L_no_first_clear", "functional-bug", "L never restarts at first (L <= L + W)",
  ("(.a(first ? 12'd0 : L)", "(.a(L)"))
m("m13_shift_low2", "functional-bug", "shift amount uses bit_sel[1:0] only (bits 4..7 mis-weighted)",
  ("x} << bit_sel)", "x} << bit_sel[1:0])"))
m("m14_rare_W_A5_b3", "functional-bug", "rare value: accumulate term off by one when W == 0xA5 and bit_sel == 3 and the v bit is set",
  ("wire [21:0] term = bit_on ? ({{13{x[8]}}, x} << bit_sel) : 22'd0;",
   "wire [21:0] term = bit_on ? (({{13{x[8]}}, x} << bit_sel) ^ {21'd0, accum_mode && W == 8'hA5 && bit_sel == 3'd3}) : 22'd0;"))
m("m15_rare_qi_80", "functional-bug", "rare value: score qi == -128 treated as +128",
  ("wire [8:0] x = accum_mode ? {1'b0, W} : {qi[7], qi};", "wire [8:0] x = accum_mode ? {1'b0, W} : (qi == 8'h80 ? 9'h080 : {qi[7], qi});"))
m("m16_powerup_init_all", "power-up", "adds power-up init values: ring, S and L start at 0",
  ("reg [20*OUTPUTS-1:0] ring;", "reg [20*OUTPUTS-1:0] ring = 0;\n    initial S = 22'sd0;\n    initial L = 12'd0;"))
m("m17_powerup_init_L", "power-up", "adds a power-up init on L only (L = 0)",
  ("reg [20*OUTPUTS-1:0] ring;", "reg [20*OUTPUTS-1:0] ring;\n    initial L = 12'd0;"))
m("m18_powerup_por_clear", "power-up", "adds an internal power-on-reset flop (init 1) that clears ring and S on the first clock",
  ("    always @(posedge clk) begin\n        ring <=",
   "    reg por = 1'b1;\n    always @(posedge clk) por <= 1'b0;\n    always @(posedge clk) begin\n        ring <="),
  ("        else if (score_en) S <= $signed(sum);\n",
   "        else if (score_en) S <= $signed(sum);\n        if (por) begin ring <= 0; S <= 22'sd0; end\n"))
m("m19_score_en_before_load", "functional-bug", "score_en has priority over load",
  ("        if (load) S <= subtract ? M : 22'sd0;\n        else if (score_en) S <= $signed(sum);",
   "        if (score_en) S <= $signed(sum);\n        else if (load) S <= subtract ? M : 22'sd0;"))
m("m20_load_M_always", "functional-bug", "load ignores subtract: pass 1 also starts from M",
  ("S <= subtract ? M : 22'sd0;", "S <= M;"))
m("m21_bit_on_no_accum_en", "functional-bug", "accumulate bit ignores accum_en: v bits add to the head in IDLE/CMD/DIV states",
  ("accum_mode ? (accum_en && v[bit_sel])", "accum_mode ? v[bit_sel]"))
m("m22_O0_zero_ext", "out-of-context-bug", "O0 zero-extended into the adder (affects only sum[21:20], i.e. S under score_en with accum_mode)",
  ("{{2{O0[19]}}, O0}", "{2'b00, O0}"))
m("m23_ring_reverse", "functional-bug", "ring rotates the other way (tail of the vector feeds the head)",
  ("ring <= {accum_mode ? sum[19:0] : O0, ring[20*OUTPUTS-1:20]};",
   "ring <= {ring[20*OUTPUTS-21:0], accum_mode ? sum[19:0] : O0};"))
m("m24_add_enable", "functional-bug", "ring only turns while accum_mode (stalls in SCORE: head/phase misaligned)",
  ("        ring <= {accum_mode ? sum[19:0] : O0, ring[20*OUTPUTS-1:20]};",
   "        if (accum_mode) ring <= {sum[19:0], ring[20*OUTPUTS-1:20]};"))
# equivalents
m("e01_plus_adder", "equivalent", "shared adder written with + instead of ripple_add",
  ("    ripple_add #(.N(22)) adder (.a(a), .b(neg ? ~term : term), .cin(neg), .s(sum));",
   "    assign sum = a + (neg ? ~term : term) + {21'd0, neg};"))
m("e02_sub_form", "equivalent", "sum = neg ? a - term : a + term",
  ("    ripple_add #(.N(22)) adder (.a(a), .b(neg ? ~term : term), .cin(neg), .s(sum));",
   "    assign sum = neg ? a - term : a + term;"))
m("e03_L_cond_form", "equivalent", "L condition written bitwise",
  ("if (accum_en && ~|sel && bit_sel == 3'd0)", "if (accum_en & (sel == 0) & ~|bit_sel)"))
m("e04_x_wide", "equivalent", "term built from 22-bit operands directly",
  ("wire [21:0] term = bit_on ? ({{13{x[8]}}, x} << bit_sel) : 22'd0;",
   "wire [21:0] xw = accum_mode ? {14'd0, W} : {{14{qi[7]}}, qi};\n    wire [21:0] term = bit_on ? (xw << bit_sel) : 22'd0;"))
m("e05_L_plus", "equivalent", "L adder written with +",
  ("    ripple_add #(.N(12)) l_adder (.a(first ? 12'd0 : L), .b({4'b0, W}), .cin(1'b0), .s(L_next));",
   "    assign L_next = (first ? 12'd0 : L) + {4'b0, W};"))

def main():
    os.makedirs(os.path.join(HERE, "mutants"), exist_ok=True)
    man = {}
    for name, cls, desc, pairs in M:
        t = G
        for old, new in pairs:
            assert t.count(old) == 1, f"{name}: {t.count(old)} matches for {old[:60]!r}"
            t = t.replace(old, new)
        assert t != G
        open(os.path.join(HERE, "mutants", name + ".v"), "w").write(f"// mutant {name}: {desc}\n" + t)
        man[name] = {"class": cls, "description": desc}
    json.dump(man, open(os.path.join(HERE, "mutants", "MANIFEST.json"), "w"), indent=1)
    print(len(man), "mutants")

if __name__ == "__main__":
    main()
