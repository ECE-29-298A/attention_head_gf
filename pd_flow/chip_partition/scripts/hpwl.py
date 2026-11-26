#!/usr/bin/env python3
"""hpwl.py <pilot_dir> [attribution.json] -- pre-route half-perimeter wirelength of <pilot_dir>/placement.cfg
(cell centres; top-level pins at their h2 DEF positions; clk excluded, rebuilt by CTS). Per cluster pair
when an attribution is given (labels as floorplan.py)."""
import json, os, re, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(__file__))
import pdlib
import floorplan as F

pdir = sys.argv[1]
inst, lab, L = F.labels(pdir, sys.argv[2] if len(sys.argv) > 2 else "analysis/h2_attribution.json")
pos = {}
for line in open(os.path.join(pdir, "placement.cfg")):
    t = line.split()
    if t:
        m = inst[t[0]][0]
        pos[t[0]] = (float(t[1]) + L[m]["w"] / 2, float(t[2]) + L[m]["h"] / 2)
D = pdlib.parse_def(F.H2DEF, want_routes=False)
nets = defaultdict(list)
for n, (m, pins) in inst.items():
    for p, v in pins.items():
        if v and v != "clk" and not v.startswith("1'b"):
            nets[v].append(n)
tot, by = 0.0, defaultdict(float)
for v, ns in nets.items():
    pts = [pos[n] for n in ns]
    if v in D["pins"]:
        pts.append((D["pins"][v]["x"], D["pins"][v]["y"]))
    if len(pts) < 2:
        continue
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    h = (max(xs) - min(xs)) + (max(ys) - min(ys))
    tot += h
    by["|".join(sorted({F.cluster_of(lab[n]) for n in ns}))] += h
print(json.dumps({"pilot": pdir, "hpwl_um": round(tot, 1), "by_cluster_set": {k: round(v, 1) for k, v in sorted(by.items(), key=lambda t: -t[1])}}))
