#!/usr/bin/env python3
"""synth_report.py <out.json> <tag> [<tag> ...]

For each shipped-flow synthesis run /Users/samuelzhang/ttharden/cpa_llsynth/<tag>, parse the
written netlist (flat or hierarchical) and recompute area with the FULL TT liberty
(pdlib.liberty_areas). Reports total area, cells, flops, area by class, and for kept
hierarchy the local area/cells/flops of every module instance plus the inter-instance nets
(bit count per pair of kept instances, counted on the flattened connectivity).
"""
import glob, json, os, re, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(__file__))
import pdlib

ROOT = "/Users/samuelzhang/ttharden/cpa_llsynth"


def cls(master):
    s = master.replace(pdlib.PFX, "")
    if s.startswith(("dff", "sdff", "latq", "icgt")):
        return "flop"
    if s.startswith(("tieh", "tiel")):
        return "tie"
    if s.startswith(("inv", "clkinv")):
        return "inv"
    if s.startswith(("buf", "clkbuf", "dly")):
        return "buf"
    return "logic"


def analyse(tag):
    d = glob.glob(f"{ROOT}/{tag}/runs/synth/*-yosys-synthesis")[0]
    nl = glob.glob(d + "/*.nl.v")[0]
    cfg = json.load(open(f"{ROOT}/{tag}/src/config_merged.json"))
    st = json.load(open(d + "/reports/stat.json"))
    mods = pdlib.parse_netlist(nl)
    A = pdlib.liberty_areas()
    top = pdlib.top_module(mods)
    cells = pdlib.flatten_cells(mods, top)
    tot = sum(A[m] for _, m, _, _ in cells)
    by_cls = Counter()
    for _, m, _, _ in cells:
        by_cls[cls(m)] += A[m]
    # local stats per instance scope (kept hierarchy only shows up as scopes)
    scope = defaultdict(lambda: {"area": 0.0, "cells": 0, "flops": 0})
    for path, m, pins, sc in cells:
        s = scope[sc or "(top)"]
        s["area"] += A[m]
        s["cells"] += 1
        s["flops"] += cls(m) == "flop"
    # inter-scope nets: a net is "between" scopes if its driver and loads are in different scopes
    OUT = {"Z", "ZN", "Q", "CO", "S"}
    drv, loads = {}, defaultdict(set)
    for path, m, pins, sc in cells:
        for p, net in pins.items():
            if net is None or net.startswith("1'b"):
                continue
            lef = pdlib.lef_macros()[m]
            if lef["dir"].get(p) == "OUTPUT":
                drv[net] = sc or "(top)"
            else:
                loads[net].add(sc or "(top)")
    top_ports = {}
    for kind, name, msb, lsb in mods[top].ports:
        for b in mods[top].bits(name):
            top_ports[b] = kind
    pair = Counter()
    for net, ls in loads.items():
        src = drv.get(net) or ("(port)" if net in top_ports else "(undriven)")
        for l in ls:
            if l != src:
                pair[(src, l)] += 1
    for net, src in drv.items():
        if net in top_ports and top_ports[net] == "output" and src != "(top)":
            pair[(src, "(port)")] += 1
    return {
        "tag": tag, "netlist": nl, "netlist_sha256_16": pdlib.sha(nl),
        "hierarchy_mode": cfg.get("SYNTH_HIERARCHY_MODE"),
        "keep_modules": cfg.get("SYNTH_KEEP_HIERARCHY_MODULES"),
        "verilog_files": cfg.get("VERILOG_FILES"),
        "modules_in_netlist": list(mods),
        "area_full_lib": round(tot, 4), "cells": len(cells),
        "flops": sum(1 for _, m, _, _ in cells if cls(m) == "flop"),
        "yosys_stat_area_h2_lib": (st.get("design") or {}).get("area"),
        "area_by_class": {k: round(v, 4) for k, v in sorted(by_cls.items())},
        "scopes": {k: {"area": round(v["area"], 4), "cells": v["cells"], "flops": v["flops"]}
                   for k, v in sorted(scope.items())},
        "inter_scope_bits": {f"{a} -> {b}": c for (a, b), c in sorted(pair.items())},
    }


def main():
    out, tags = sys.argv[1], sys.argv[2:]
    res = {t: analyse(t) for t in tags}
    old = json.load(open(out)) if os.path.exists(out) else {}
    old.update(res)
    json.dump(old, open(out, "w"), indent=1)
    base = old.get("a_flat", {}).get("area_full_lib")
    for t in tags:
        r = res[t]
        dlt = f"{r['area_full_lib'] - base:+9.1f}" if base else ""
        print(f"{t:14s} {r['area_full_lib']:10.1f} {dlt} cells {r['cells']:5d} flops {r['flops']:4d} "
              f"sha {r['netlist_sha256_16']} scopes {len(r['scopes'])}")


if __name__ == "__main__":
    main()
