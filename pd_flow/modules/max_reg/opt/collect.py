#!/usr/bin/env python3
"""collect.py: gather lint / EQY / contract / module area / shipped-flow chip area / in-context
max_reg cone for every candidate, variant and noise run -> runs/collected.json + table."""
import json, os, re, glob, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = 41116.096
def cone(name):
    nl = os.path.join(HERE, "shipped_flow", name + ".nl.v")
    if not os.path.exists(nl): return None
    out = subprocess.run(["python3", os.path.join(HERE, "cone.py"), nl], capture_output=True, text=True).stdout
    return float(re.search(r"max_reg_total=([\d.]+)", out).group(1))
rows = []
for kind, pat in [("candidate", "candidates/c*.v"), ("noise", "noise/n*.v"), ("variant", "variants/*.v"), ("negctl", "negctl/*.v"), ("final_text", "c10_clean/max_reg.v")]:
    for f in sorted(glob.glob(os.path.join(HERE, pat))):
        n = "c10_clean" if kind == "final_text" else os.path.basename(f)[:-2]
        d = os.path.join(HERE, "runs", n); r = {"name": n, "kind": kind, "file": os.path.relpath(f, HERE)}
        lf = os.path.join(d, "lint.log")
        if os.path.exists(lf): r["lint_rc"] = int(re.search(r"rc=(\d+)", open(lf).read().splitlines()[-1]).group(1))
        ef = os.path.join(d, "eqy", "eqy.log")
        if os.path.exists(ef):
            t = open(ef).read(); m = re.findall(r"DONE \((\w+)", t)
            r["eqy"] = m[-1] if m else "ERROR"; r["eqy_partitions_proved"] = len(re.findall(r"Successfully proved equivalence of partition", t))
        cf = os.path.join(d, "contract", "results.json")
        if os.path.exists(cf):
            c = json.load(open(cf)); r["contract"] = f'{c["items_ok"]}/{c["items_total"]}'; r["contract_all_ok"] = c["all_ok"]
        af = os.path.join(d, "area.json")
        if os.path.exists(af):
            a = {x["module"]: x for x in json.load(open(af))["results"]}
            r["module_area_synth_area"] = a["max_reg"]["area_um2"]; r["module_cells"] = a["max_reg"]["cells"]
            r["top_area_synth_area"] = a["tt_um_attention_head_gf"]["area_um2"]
        sf = os.path.join(HERE, "shipped_flow", n + ".txt")
        if os.path.exists(sf):
            p = open(sf).read().split()
            if len(p) >= 3:
                r["chip_area_shipped"] = float(p[-2]); r["chip_cells_shipped"] = int(p[-1])
                r["chip_delta"] = round(r["chip_area_shipped"] - BASE, 4)
                mc = cone(n); r["max_reg_in_context"] = mc; r["rest_of_chip"] = round(r["chip_area_shipped"] - mc, 4)
        rows.append(r)
json.dump(rows, open(os.path.join(HERE, "runs", "collected.json"), "w"), indent=1)
for r in rows:
    print(f'{r["name"]:20s} {r["kind"]:9s} lint={r.get("lint_rc","-")} eqy={r.get("eqy","-"):5s} contract={r.get("contract","-"):6s} '
          f'mod={r.get("module_area_synth_area",0):8.1f} chip={r.get("chip_area_shipped",0):9.1f} d={r.get("chip_delta",0):+7.1f} '
          f'mr_ctx={r.get("max_reg_in_context") or 0:7.1f} rest={r.get("rest_of_chip",0):8.1f}')
