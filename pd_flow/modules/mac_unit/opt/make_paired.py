#!/usr/bin/env python3
"""make_paired.py <cand>... [--only n1,n2,...]: apply the golden structural rewrites n* of make_cands.VARS
(n3 and n5 excluded: n3 gives the golden netlist, n5 swaps in a multiplier) on top of each candidate ->
variants/<cand>_<nK>.v, only where the rewritten line is untouched by the candidate. <cand> = c00_golden
gives the golden's own variant (identical text to variants/nK_*.v)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_cands import CANDS, VARS, apply, H
args = sys.argv[1:]
NS = [k for k in VARS if k.startswith("n") and not k.startswith(("n3_", "n5_"))]
if "--only" in args:
    i = args.index("--only"); want = args[i + 1].split(","); args = args[:i] + args[i + 2:]
    NS = [k for k in NS if k.split("_")[0] in want]
for c in args:
    base = apply(CANDS[c]) if c in CANDS else apply([])
    for v in NS:
        try: t = apply(VARS[v], base)
        except AssertionError: continue
        n = f"{c}_{v.split('_')[0]}"
        open(os.path.join(H, "variants", n + ".v"), "w").write(t); print(n)
