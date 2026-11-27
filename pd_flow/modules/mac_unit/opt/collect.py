#!/usr/bin/env python3
"""collect.py: attempts.json from shipped_flow/*.txt + *.cone.json (x0 shipped flow, both contexts) and the
verification lines in runs/verify_*.txt. Context 'orig' = baseline/original_rtl; 'c06' = original_rtl with the
accepted divider c06 (opt/base_c06). Deltas are against the golden text in the same context."""
import json, glob, os, re
H = os.path.dirname(os.path.abspath(__file__))
KIND = lambda n: ("golden" if n == "c00_golden" else "golden-rewrite" if re.match(r"^(v\d|n\d|c00_golden_n)", n)
                  else "candidate" if re.match(r"^c\d", n) and "_n" not in n.split("_")[-1][:2] and not re.search(r"_n\d+$", n)
                  else "candidate-rewrite" if re.match(r"^c\d", n) else "probe" if n.startswith("p") else
                  "proposal" if n.startswith("g") else "negctl")
rows = []
for t in sorted(glob.glob(os.path.join(H, "shipped_flow", "*.txt"))):
    base = os.path.basename(t)[:-4]
    name, ctx = (base.split("@") + ["orig"])[:2]
    line = open(t).read().strip().splitlines()[-1].split()
    cj = os.path.join(H, "shipped_flow", base + ".cone.json")
    c = json.load(open(cj)) if os.path.exists(cj) and os.path.getsize(cj) else {}
    rows.append({"name": name, "context": ctx, "kind": KIND(name), "chip_um2": float(line[1]), "cells": int(line[2]),
                 "mac_um2": c.get("mac_area"), "mac_flops": c.get("mac_flops"), "mac_logic_um2": c.get("mac_logic_area"),
                 "exp_um2": c.get("exp_area"), "shared_um2": c.get("shared_area"), "rest_um2": c.get("rest_area"),
                 "netlist_sha256": c.get("sha")})
gold = {r["context"]: r for r in rows if r["name"] == "c00_golden"}
for r in rows:
    g = gold[r["context"]]
    r["d_chip"] = round(r["chip_um2"] - g["chip_um2"], 4)
    r["d_mac"] = round(r["mac_um2"] - g["mac_um2"], 4) if r["mac_um2"] is not None else None
ver = {}
for f in glob.glob(os.path.join(H, "runs", "verify_*.txt")):
    for l in open(f):
        if l.strip(): ver[l.split()[0]] = l.strip()
for r in rows:
    if r["name"] in ver: r["verify"] = ver[r["name"]]
desc = json.load(open(os.path.join(H, "descriptions.json")))
for r in rows:
    k = re.sub(r"_n\d+$", "", r["name"])
    r["description"] = desc.get(r["name"]) or (desc.get(k, "") + (f" + golden rewrite {r['name'].split('_')[-1]}" if k != r["name"] else ""))
json.dump({"flow": "LibreLane 3.0.14 Yosys.Synthesis, shipping x0 config (ll_synth_x0.sh); cone rule in cone.py",
           "golden": {k: {"chip_um2": v["chip_um2"], "mac_um2": v["mac_um2"], "sha": v["netlist_sha256"]} for k, v in gold.items()},
           "attempts": rows}, open(os.path.join(H, "attempts.json"), "w"), indent=1)
print(len(rows), "rows")
