#!/usr/bin/env python3
"""Compare the intended adder placement (out/chip_anchor_n*.json) with a DEF from a harden run:
per instance status, master, location, orientation and displacement. Asserts the placement
'took effect' (experiments.md section 6). Usage: check_placed.py <def> [<def> ...] -> JSON on stdout."""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from defparse import read_def

def esc(n):
    return re.sub(r"([\[\]])", r"\\\1", n)

want = {}
for n in (22, 12):
    want.update(json.load(open(os.path.join(HERE, "..", "out", f"chip_anchor_n{n}.json")))["placement"])
res = {}
for d in sys.argv[1:]:
    comps, _, _ = read_def(d)
    rows = []
    for name, w in want.items():
        c = comps.get(esc(name)) or comps.get(name)
        if c is None:
            rows.append({"inst": name, "found": False}); continue
        dx = c["x"] - w["location"][0]; dy = c["y"] - w["location"][1]
        rows.append({"inst": name, "found": True, "status": c["status"], "master": c["master"].split("__")[-1],
                     "x": c["x"], "y": c["y"], "orient": c["orient"], "want_orient": w["orientation"],
                     "dx": round(dx, 3), "dy": round(dy, 3)})
    found = [r for r in rows if r["found"]]
    exact = [r for r in found if r["dx"] == 0 and r["dy"] == 0 and r["orient"] == r["want_orient"]]
    res[d] = {"instances": len(want), "found": len(found), "exact": len(exact),
              "moved": [r for r in found if r not in exact],
              "statuses": sorted({r["status"] for r in found}), "masters": sorted({r["master"] for r in found}),
              "max_abs_displacement_um": max([abs(r["dx"]) + abs(r["dy"]) for r in found] or [0])}
print(json.dumps(res, indent=1))
