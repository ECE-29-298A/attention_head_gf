#!/usr/bin/env python3
"""check_placed.py <chip_anchor.cfg> <pnl.v|-> <def> [<def> ...] -> JSON on stdout.
For every cfg line (name x y orient): found / status / master / exact location and orientation in each DEF,
and, if a netlist is given, the net on the instance's Q pin (placement-only variants must still sit on the
intended max_reg / mac_unit register bit: names.json Q net). Asserts the fixed placement took effect."""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from defparse import read_def
cfgf, nlf, defs = sys.argv[1], sys.argv[2], sys.argv[3:]
want = [l.split() for l in open(cfgf) if l.strip()]
qnet = {}
if nlf != "-":
    for m in re.finditer(r'gf180mcu_fd_sc_mcu7t5v0__(\w+)\s+(\S+)\s*\((.*?)\);', open(nlf).read(), re.S):
        q = re.search(r'\.Q\(\s*\\?(\S+?)\s*\)', m.group(3))
        qnet[m.group(2).lstrip("\\")] = (m.group(1), q.group(1) if q else None)
esc = lambda n: re.sub(r"([\[\]])", r"\\\1", n)
res = {"cfg": cfgf, "netlist": nlf, "defs": {}}
for d in defs:
    comps, _, _ = read_def(d)
    rows = []
    for name, x, y, o in want:
        c = comps.get(esc(name)) or comps.get(name)
        if c is None:
            rows.append({"inst": name, "found": False}); continue
        rows.append({"inst": name, "found": True, "status": c["status"], "master": c["master"].split("__")[-1],
                     "dx": round(c["x"] - float(x), 3), "dy": round(c["y"] - float(y), 3), "orient": c["orient"],
                     "want_orient": o})
    found = [r for r in rows if r["found"]]
    exact = [r for r in found if r["dx"] == 0 and r["dy"] == 0 and r["orient"] == r["want_orient"]]
    res["defs"][d] = {"instances": len(want), "found": len(found), "exact": len(exact),
                      "statuses": sorted({r["status"] for r in found}), "masters": sorted({r["master"] for r in found}),
                      "moved": [r for r in found if r not in exact][:10]}
if qnet:
    res["q_nets"] = {n: qnet.get(n) for n, *_ in want}
print(json.dumps(res, indent=1))
