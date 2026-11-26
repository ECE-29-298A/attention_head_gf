#!/usr/bin/env python3
"""make_variants.py <src.v> <outdir>: cosmetic (function-preserving) rewrites for the noise band.
Each rewrite is asserted to apply exactly once; EQY proves every variant against the golden."""
import sys, os, re
src, out = sys.argv[1], sys.argv[2]
t = open(src).read()
name = os.path.basename(src)[:-2]
def sub(s, a, b, n=1):
    assert s.count(a) == n, (name, a, s.count(a)); return s.replace(a, b)
R = {}
# v1: swap the order of the two halves of the datapath always block
def v1(s):
    a = next(l + "\n" for l in s.split("\n") if l.startswith(("        quotient <= ", "        dq <= ")))
    b = "        remainder_value <= state == IDLE ? 12'd0 : next_remainder;\n"
    c = "        step <= state == IDLE ? 5'd0 : step + 5'd1;\n"
    return sub(s, a + b + c, c + b + a)
# v2: state == IDLE written as !busy inside the datapath block
def v2(s):
    return s.replace("quotient <= state == IDLE ?", "quotient <= !busy ?").replace("dq <= state == IDLE ?", "dq <= !busy ?").replace(
        "remainder_value <= state == IDLE ?", "remainder_value <= !busy ?").replace(
        "step <= state == IDLE ?", "step <= !busy ?")
# v3: subtract via ==
def v3(s): return sub(s, "wire subtract = !difference[13];", "wire subtract = difference[13] == 1'b0;")
# v4: case items reversed (ROUND, DIVIDE, IDLE)
def v4(s):
    i = s.index("                IDLE: if (start)"); j = s.index("                default:")
    body = s[i:j]
    k1 = body.index("                DIVIDE:"); k2 = body.index("                ROUND:")
    return s[:i] + body[k2:] + body[k1:k2] + body[:k1] + s[j:]
# v5: magnitude written as a conditional negate
def v5(s): return sub(s, "wire [18:0] magnitude = sum_in[19] ? (~sum_in[18:0] + 19'd1) : sum_in[18:0];",
                      "wire [18:0] magnitude = (sum_in[18:0] ^ {19{sum_in[19]}}) + {18'd0, sum_in[19]};")
# v6: next_remainder mux inverted
def v6(s): return sub(s, "wire [11:0] next_remainder = subtract ? difference[11:0] : trial[11:0];",
                      "wire [11:0] next_remainder = !subtract ? trial[11:0] : difference[11:0];")
for k, f in [("v1", v1), ("v2", v2), ("v3", v3), ("v4", v4), ("v5", v5), ("v6", v6)]:
    try: r = f(t)
    except (AssertionError, ValueError) as e: print("skip", k, str(e)[:60]); continue
    if r == t: print("skip", k, "no change"); continue
    open(os.path.join(out, f"{name}_{k}.v"), "w").write(r)
