#!/usr/bin/env python3
"""Collect per-candidate results from runs/<name>/ into a table (stdout) and rows (JSON)."""
import json, os, re, glob, sys
HERE = os.path.dirname(os.path.abspath(__file__))
rows = []
for d in sorted(glob.glob(os.path.join(HERE, "runs", "*"))):
    n = os.path.basename(d)
    if not os.path.exists(os.path.join(d, "contract", "results.json")):
        continue
    r = {"name": n}
    a = {x["module"]: x for x in json.load(open(os.path.join(d, "area.json")))["results"]}
    for k, key in [("ripple_add_22", "a22"), ("ripple_add_12", "a12"), ("mac_unit", "mac"), ("tt_um_attention_head_gf", "top")]:
        r[key] = a[k]["area_um2"]; r[key + "_cells"] = a[k]["cells"]
    c = json.load(open(os.path.join(d, "contract", "results.json")))
    r["contract"] = f'{c["items_ok"]}/{c["items_total"]}'; r["contract_all_ok"] = c["all_ok"]
    r["contract_failed_items"] = [i["id"] for i in c["items"] if not i["ok"]]
    for w in (12, 22):
        t = open(os.path.join(d, "eqy", f"eqy_n{w}.log")).read()
        m = re.findall(r"DONE \((\w+)", t)
        r[f"eqy_n{w}"] = m[-1] if m else "ERROR"
        r[f"eqy_n{w}_partitions_proved"] = len(re.findall(r"Successfully proved equivalence of partition", t))
    for w in (12, 22):
        for corner in ("tt_025C_3v30", "ss_125C_3v00"):
            f = os.path.join(d, "sta", f"sta_n{w}_{corner}.log")
            if os.path.exists(f):
                m = re.search(r"worst_arrival_ns=([\d.]+) startpoint=(\S+) endpoint=(\S+)", open(f).read())
                r[f"t{w}_{corner[:2]}"] = float(m.group(1)); r[f"t{w}_{corner[:2]}_path"] = f"{m.group(2)}->{m.group(3)}"
    rows.append(r)
json.dump(rows, open(os.path.join(HERE, "runs", "collected.json"), "w"), indent=1)
g = next(r for r in rows if r["name"] == "golden")
print(f'{"name":20s} {"a22":>9s} {"a12":>9s} {"mac":>10s} {"top":>10s} {"tt22":>7s} {"ss22":>7s} {"contract":>8s} eqy12 eqy22')
for r in rows:
    print(f'{r["name"]:20s} {r["a22"]:9.2f} {r["a12"]:9.2f} {r["mac"]:10.2f} {r["top"]:10.2f} {r["t22_tt"]:7.3f} {r["t22_ss"]:7.3f} {r["contract"]:>8s} {r["eqy_n12"]} {r["eqy_n22"]}'
          f'  d22={r["a22"]-g["a22"]:+.1f} d12={r["a12"]-g["a12"]:+.1f} dtop={r["top"]-g["top"]:+.1f} dtt={100*(r["t22_tt"]/g["t22_tt"]-1):+.1f}% dss={100*(r["t22_ss"]/g["t22_ss"]-1):+.1f}%')
