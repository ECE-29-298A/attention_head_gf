#!/usr/bin/env python3
"""make_variants.py <cand.v> <prefix>: four cosmetic rewrites of the load expression
(v1 or-swap, v2 and-swap, v3 bitwise ops, v4 nested if) -> variants/<prefix>_v<k>.v.
Used identically for the golden (noise band) and for candidates (candidate spread)."""
import re, sys
src = open(sys.argv[1]).read(); pre = sys.argv[2]
if "wire load" not in src:  # golden form: introduce the load wire first (bit-identical, n04)
    src = src.replace("always @(posedge clk) begin\n    if (en && (first || S_in > M)) begin\n        M <= S_in;\n    end\nend",
                      "wire load = en && (first || S_in > M);\n\nalways @(posedge clk) begin\n    if (load) M <= S_in;\nend")
m = re.search(r"wire load = en && \(first \|\| (.*)\);\n", src); X = m.group(1)
ff = "always @(posedge clk) begin\n    if (load) M <= S_in;\nend"
v = {1: src.replace(m.group(0), f"wire load = en && ({X} || first);\n"),
     2: src.replace(m.group(0), f"wire load = (first || {X}) && en;\n"),
     3: src.replace(m.group(0), f"wire load = en & (first | ({X}));\n"),
     4: src.replace(m.group(0), f"wire cmp = {X};\n").replace(ff, "always @(posedge clk) begin\n    if (en) begin\n        if (first || cmp) M <= S_in;\n    end\nend")}
for k, s in v.items():
    assert s != src, k
    open(f"variants/{pre}_v{k}.v", "w").write(s)
# second batch (v5..v8), same rule for golden and candidates
v2nd = {5: src.replace(m.group(0), f"wire load = (en && first) || (en && {X});\n"),
        6: src.replace(m.group(0), f"wire load = en ? (first || {X}) : 1'b0;\n"),
        7: src.replace(ff, "always @(posedge clk) begin\n    if (load) M <= S_in;\n    else M <= M;\nend"),
        8: src.replace(ff, "wire signed [21:0] M_next = load ? S_in : M;\n\nalways @(posedge clk) begin\n    M <= M_next;\nend")}
for k, s in v2nd.items():
    assert s != src, k
    open(f"variants/{pre}_v{k}.v", "w").write(s)
