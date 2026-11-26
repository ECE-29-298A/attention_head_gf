#!/usr/bin/env python3
"""collect.py: gather every evaluated text (candidates/ and variants/) into runs/collected.json:
verification (runs/<n>/), synth_area module area (runs/<n>/area.json), module-level shipped flow
(shipped_flow/module/<n>.stat.json), chip-level shipped flow (shipped_flow/<n>.stat.json) and the
in-context cone split (shipped_flow/<n>.cone.json). Also prints a per-family summary."""
import glob, hashlib, json, os, re, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__))
GOLD_CHIP = 41116.096


def stat(p):
    if not os.path.exists(p): return None
    d = json.load(open(p)); t = d.get("design") or next(iter(d["modules"].values()))
    return {"area": t["area"], "cells": t["num_cells"]}


def verif(n):
    d = os.path.join(HERE, "runs", n); r = {}
    for R in (0, 1):
        lp = os.path.join(d, f"lint_R{R}.log")
        if os.path.exists(lp): r[f"lint_R{R}"] = open(lp).read().strip().split("\n")[-1]
        ep = os.path.join(d, f"eqy_R{R}", "eqy.log")
        if os.path.exists(ep):
            t = open(ep).read(); m = re.findall(r"DONE \((\w+)", t)
            r[f"eqy_R{R}"] = m[-1] if m else "none"
    bx = os.path.join(d, "blocks", "results.xml")
    if os.path.exists(bx):
        t = open(bx).read(); r["blocks"] = "pass" if "testcase" in t and "<failure" not in t else "FAIL"
    return r


rows = []
for f in sorted(glob.glob(os.path.join(HERE, "candidates", "*.v")) + glob.glob(os.path.join(HERE, "variants", "*.v"))):
    n = os.path.basename(f)[:-2]
    row = {"name": n, "family": n.split("_v")[0] if re.search(r"_v\d+$", n) else n,
           "file": os.path.relpath(f, HERE), "sha256": hashlib.sha256(open(f, "rb").read()).hexdigest()}
    row.update(verif(n))
    a = os.path.join(HERE, "runs", n, "area.json")
    if os.path.exists(a): row["synth_area_module"] = json.load(open(a))["results"][0]["area_um2"]
    m = stat(os.path.join(HERE, "shipped_flow", "module", n + ".stat.json"))
    if m: row["ll_module_area"] = m["area"]
    c = stat(os.path.join(HERE, "shipped_flow", n + ".stat.json"))
    if c:
        row["chip_area"] = c["area"]; row["chip_cells"] = c["cells"]; row["chip_delta"] = round(c["area"] - GOLD_CHIP, 4)
    cj = os.path.join(HERE, "shipped_flow", n + ".cone.json")
    if os.path.exists(cj) and os.path.getsize(cj):
        r = json.load(open(cj)); row.update(exp_incontext=r["exp_area"], exp_cells=r["exp_cells"],
                                            shared_dOnly=r["shared_dOnly_area"], rest=r["rest_area"])
    rows.append(row)
json.dump(rows, open(os.path.join(HERE, "runs", "collected.json"), "w"), indent=1)

fam = {}
for r in rows: fam.setdefault(r["family"], []).append(r)
print(f"{'family':24s} {'n':>2s} {'ok':>3s} {'synthA':>7s} {'llmod':>14s} {'chip min/med/max':>26s} {'exp min/med/max':>22s}")
for k, rs in fam.items():
    ok = sum(1 for r in rs if r.get("eqy_R0") == "PASS" and r.get("eqy_R1") == "PASS" and r.get("blocks") == "pass")
    ch = [r["chip_area"] for r in rs if "chip_area" in r]; ex = [r["exp_incontext"] for r in rs if "exp_incontext" in r]
    lm = [r["ll_module_area"] for r in rs if "ll_module_area" in r]
    sa = [r["synth_area_module"] for r in rs if "synth_area_module" in r]
    f3 = lambda v: f"{min(v):8.1f}/{st.median(v):8.1f}/{max(v):8.1f}" if v else "-"
    f2 = lambda v: f"{min(v):6.0f}/{st.median(v):6.0f}" if v else "-"
    print(f"{k:24s} {len(rs):2d} {ok:3d} {sa[0] if sa else 0:7.0f} {f2(lm):>14s} {f3(ch):>26s} {f3(ex):>22s}")
