#!/usr/bin/env python3
"""make_variants_phase.py <src.v> <outdir>: extra cosmetic rewrites for phase-counter candidates (c04 family):
w1 swap the dq/remainder register lines; w2 phase transition as nested if; w3 idle as ~|phase;
w4 next_remainder mux written with the select inverted; w5 phase increment written as phase + 1'b1 in a case."""
import sys, os
src, out = sys.argv[1], sys.argv[2]; t = open(src).read(); name = os.path.basename(src)[:-2]
def sub(s, a, b):
    assert s.count(a) == 1, (a, s.count(a)); return s.replace(a, b)
A = "        dq <= idle ? magnitude : next_dq;\n"; B = "        remainder_value <= idle ? 12'd0 : next_remainder;\n"
T = "            phase <= idle ? {4'd0, start} : round_step ? 5'd0 : phase + 5'd1;\n"
V = {
 "w1": lambda s: sub(s, A + B, B + A),
 "w2": lambda s: sub(s, T, "            if (idle) phase <= {4'd0, start};\n            else if (round_step) phase <= 5'd0;\n            else phase <= phase + 5'd1;\n"),
 "w3": lambda s: sub(s, "    wire idle = phase == 5'd0;\n", "    wire idle = ~|phase;\n"),
 "w4": lambda s: sub(s, "    wire [11:0] next_remainder = subtract ? difference[11:0] : trial[11:0];",
                       "    wire [11:0] next_remainder = !subtract ? trial[11:0] : difference[11:0];"),
 "w5": lambda s: sub(s, T, "            case (1'b1)\n                idle: phase <= {4'd0, start};\n                round_step: phase <= 5'd0;\n                default: phase <= phase + 5'd1;\n            endcase\n"),
}
for k, f in V.items():
    try: r = f(t); open(os.path.join(out, f"{name}_{k}.v"), "w").write(r)
    except AssertionError as e: print("skip", k, e)
