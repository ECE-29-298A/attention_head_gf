#!/usr/bin/env python3
"""collect.py: shipped_flow/*.txt + *.cone.json (+ runs/<name>/verify.txt, eqy notes) -> attempts.json.
Chip area = stat.json (judge, x0 config); div/shared/rest = cone.py split (Liberty tt areas)."""
import json, glob, os, re
H = os.path.dirname(os.path.abspath(__file__))
DESC = json.load(open(os.path.join(H, "descriptions.json")))
rows = []
for t in sorted(glob.glob(os.path.join(H, "shipped_flow", "*.txt"))):
    n = os.path.basename(t)[:-4]
    line = open(t).read().strip().splitlines()[-1].split()
    if len(line) != 3: continue
    cj = os.path.join(H, "shipped_flow", n + ".cone.json")
    c = json.load(open(cj)) if os.path.exists(cj) and os.path.getsize(cj) else {}
    base = re.sub(r"_(v|w)\d+$", "", n)
    v = os.path.join(H, "runs", n, "verify.txt")
    rows.append({"name": n, "family": base, "variant": n[len(base) + 1:] or "base",
                 "description": DESC.get(base, ""), "chip_area": float(line[1]), "cells": int(line[2]),
                 "div_area": c.get("div_area"), "div_flops": c.get("div_flops"), "div_logic_area": c.get("div_logic_area"),
                 "shared_area": c.get("shared_area"), "rest_area": c.get("rest_area"), "netlist_sha256": c.get("sha"),
                 "verify": open(v).read().strip() if os.path.exists(v) else "not run"})
g = next(r for r in rows if r["name"] == "c00_golden")
for r in rows:
    r["d_chip"] = round(r["chip_area"] - g["chip_area"], 4)
    r["d_div"] = round(r["div_area"] - g["div_area"], 4) if r["div_area"] is not None else None
json.dump({"config": "x0 (h2 + mux2_1), /Users/samuelzhang/ttharden/md_x0_full", "golden_chip": g["chip_area"],
           "golden_div": g["div_area"], "attempts": rows}, open(os.path.join(H, "attempts.json"), "w"), indent=1)
for r in rows: print(f'{r["name"]:34s} chip {r["chip_area"]:9.1f} ({r["d_chip"]:+7.1f}) div {r["div_area"]:7.1f} ({r["d_div"]:+6.1f}) ff {r["div_flops"]} rest {r["rest_area"]:8.1f}')
