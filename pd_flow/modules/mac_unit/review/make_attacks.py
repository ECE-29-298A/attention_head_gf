#!/usr/bin/env python3
"""Agent 2: contract-attack candidates x04-x06 (x01-x03 and c_rename were made by hand from the golden
with `ring` renamed `rr`). Writes attacks/*.v and attacks/MANIFEST.json."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__)); A = os.path.join(HERE, "attacks")
g = open(os.path.join(HERE, "golden_copy", "mac_unit.v")).read()
def rep(t, o, n):
    assert t.count(o) == 1, o; return t.replace(o, n)
bug = ("wire [21:0] term = bit_on ? ({{13{x[8]}}, x} << bit_sel) : 22'd0;",
       "wire [21:0] term = bit_on ? (({{13{x[8]}}, x} << bit_sel) ^ {21'd0, accum_mode && W == 8'hA5 && bit_sel == 3'd3}) : 22'd0;")
x4 = rep(rep(g, *bug), "    assign O0 = ring[19:0];\n", "    assign O0 = ring[19:0];\n    always @* assume (!(W == 8'hA5 && bit_sel == 3'd3));\n")
open(os.path.join(A, "x04_plain_assume_rare.v"), "w").write("// mutant x04: m14 rare bug + plain (no ifdef) assume hiding it\n" + x4)
x5 = rep(g, "    assign O0 = ring[19:0];", "    reg pf;\n    always @(posedge clk) pf <= 1'b1;\n    assign O0 = pf ? ring[19:0] : ring[19:0] ^ {12'd0, W};")
x5 = rep(x5, "wire [21:0] a = accum_mode ? (load_o ? 22'd0 : {{2{O0[19]}}, O0}) : S;", "wire [21:0] a = accum_mode ? (load_o ? 22'd0 : {{2{ring[19]}}, ring[19:0]}) : S;")
x5 = rep(x5, "ring <= {accum_mode ? sum[19:0] : O0, ring[20*OUTPUTS-1:20]};", "ring <= {accum_mode ? sum[19:0] : ring[19:0], ring[20*OUTPUTS-1:20]};")
open(os.path.join(A, "x05_powerup_flag_O0.v"), "w").write("// mutant x05: extra no-init flop pf (1 after the first edge); while pf==0 (power-up cycle only) O0 = head ^ W\n" + x5)
x5b = rep(g, "    assign O0 = ring[19:0];", "    reg pf;\n    always @(posedge clk) pf <= 1'b1;\n    assign O0 = pf ? ring[19:0] : ring[19:0] ^ {12'd0, W};")
open(os.path.join(A, "x05b_powerup_flag_O0_consistent.v"), "w").write("// mutant x05b: as x05 but the ring consumes the garbled O0 (behaviour = golden from another power-up state)\n" + x5b)
x6 = rep(g, "    always @(posedge clk) begin\n        ring <=", "    reg pf;\n    always @(posedge clk) pf <= 1'b1;\n    always @(posedge clk) begin\n        ring <=")
x6 = rep(x6, "        else if (score_en) S <= $signed(sum);", "        else if (score_en) S <= $signed(sum);\n        else if (!pf) S <= ~S;")
open(os.path.join(A, "x06_powerup_flag_S.v"), "w").write("// mutant x06: extra no-init flop pf; at the power-up edge (pf==0) without load/score_en, S inverts\n" + x6)
man = {"c_rename": {"class": "equivalent", "description": "ring renamed rr"},
 "x01_rename_rare_formal_assume": {"class": "functional-bug", "description": "rename + rare bug + ifdef FORMAL assume"},
 "x02_rename_rare": {"class": "functional-bug", "description": "rename + rare bug"},
 "x03_rename_init": {"class": "power-up", "description": "rename + init values"},
 "x04_plain_assume_rare": {"class": "functional-bug", "description": "rare bug + plain assume"},
 "x05_powerup_flag_O0": {"class": "power-up-only", "description": "no-init power-up flag changes O0 in the first cycle only"},
 "x05b_powerup_flag_O0_consistent": {"class": "power-up-equivalent", "description": "no-init power-up flag garbles O0 at cycle 0 consistently (inside the golden's free power-up behaviour)"},
 "x06_powerup_flag_S": {"class": "power-up", "description": "no-init power-up flag changes S at the first edge (pre-flush)"}}
json.dump(man, open(os.path.join(A, "MANIFEST.json"), "w"), indent=1)
