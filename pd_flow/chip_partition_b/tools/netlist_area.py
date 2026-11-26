#!/usr/bin/env python3
"""netlist_area.py <yosys .nl.v.json> [--json OUT]: cell area of a synthesized netlist with the FULL
tt Liberty (stat.json under EXTRA_EXCLUDED_CELLS omits excluded masters, e.g. the 6 synthesis buf_2).
Hierarchical netlists: per module (own cells only) and per instance path (own cells), plus totals."""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdlib import liberty, yosys_json, module_cells, cell_class, PFX, sha
def main():
    p = sys.argv[1]
    lib = liberty()
    d = yosys_json(p)
    mods = d["modules"]
    top = [n for n, m in mods.items() if m.get("attributes", {}).get("top")]
    top = top[0] if top else [n for n in mods if not n.startswith(PFX)][0]
    own = {}
    for mn, m in mods.items():
        if mn.startswith(PFX) or m.get("attributes", {}).get("blackbox"): continue
        a = {"area": 0.0, "cells": 0, "seq": 0, "by_class": {}, "by_type": {}, "subs": []}
        for n, t, conn, _ in module_cells(m):
            if t in lib:
                ar = lib[t]["area"]; k = cell_class(t)
                a["area"] += ar; a["cells"] += 1; a["seq"] += k == "seq"
                a["by_class"][k] = round(a["by_class"].get(k, 0) + ar, 4)
                a["by_type"][t] = a["by_type"].get(t, 0) + 1
            elif t in mods:
                a["subs"].append((n, t))
            else:
                raise SystemExit(f"unknown cell type {t}")
        a["area"] = round(a["area"], 4)
        own[mn] = a
    inst = {}
    def walk(path, mn):
        a = own[mn]
        inst[path] = {"module": mn, "area": a["area"], "cells": a["cells"], "seq": a["seq"], "by_class": a["by_class"]}
        tot = [a["area"], a["cells"], a["seq"]]
        for cn, ct in a["subs"]:
            t = walk(path + "/" + cn, ct)
            tot = [x + y for x, y in zip(tot, t)]
        inst[path]["total_area"] = round(tot[0], 4); inst[path]["total_cells"] = tot[1]; inst[path]["total_seq"] = tot[2]
        return tot
    tot = walk(top, top)
    res = {"netlist_json": p, "sha16": sha(p), "top": top, "total_area": round(tot[0], 4), "total_cells": tot[1],
           "total_seq": tot[2], "instances": inst}
    if "--json" in sys.argv:
        json.dump(res, open(sys.argv[sys.argv.index("--json") + 1], "w"), indent=1)
    print(f"{os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(p))))}: total {tot[0]:.4f} um2, {tot[1]} cells, {tot[2]} flops")
    for k, v in inst.items():
        print(f"  {k:60s} own {v['area']:10.2f} ({v['cells']:4d} c, {v['seq']:3d} ff)  total {v['total_area']:10.2f}")
main()
