#!/usr/bin/env python3
"""Scrape harden metrics for every chip_runs/<tag>/harden/metrics.json (plus the stored
pd_flow/baseline/harden as 'baseline_stored') into chip_runs/harden_table.json and print a table."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)) + "/.."
runs = {"baseline_stored": os.path.join(HERE, "../../../baseline/harden/metrics.json")}
for t in sorted(os.listdir(os.path.join(HERE, "chip_runs"))):
    p = os.path.join(HERE, "chip_runs", t, "harden", "metrics.json")
    if os.path.exists(p): runs[t] = p
CORN = ["max_ss_125C_3v00", "nom_ss_125C_3v00", "min_ss_125C_3v00", "max_tt_025C_3v30", "nom_tt_025C_3v30",
        "min_tt_025C_3v30", "max_ff_n40C_3v60", "nom_ff_n40C_3v60", "min_ff_n40C_3v60"]
KEYS = ["design__instance__area__stdcell", "design__instance__utilization", "design__instance__count__stdcell",
        "design__instance__area__class:timing_repair_buffer", "design__instance__count__class:timing_repair_buffer",
        "timing__setup__ws", "timing__hold__ws", "timing__setup_vio__count", "timing__hold_vio__count",
        "design__max_slew_violation__count", "design__max_cap_violation__count", "design__max_fanout_violation__count",
        "route__wirelength", "route__drc_errors", "route__antenna_violation__count", "magic__drc_error__count",
        "design__lvs_error__count", "magic__illegal_overlap__count", "power__total", "power__internal__total",
        "power__switching__total", "power__leakage__total", "design__disconnected_pin__count"]
tab = {}
for t, p in runs.items():
    m = json.load(open(p)); r = {k: m.get(k) for k in KEYS}
    for c in CORN:
        r[f"setup_ws:{c}"] = m.get(f"timing__setup__ws__corner:{c}")
        r[f"hold_ws:{c}"] = m.get(f"timing__hold__ws__corner:{c}")
    r["max_slew:max_ss"] = m.get("design__max_slew_violation__count__corner:max_ss_125C_3v00")
    r["max_slew:max_tt"] = m.get("design__max_slew_violation__count__corner:max_tt_025C_3v30")
    r["source"] = os.path.relpath(p, HERE)
    tab[t] = r
json.dump(tab, open(os.path.join(HERE, "chip_runs", "harden_table.json"), "w"), indent=1)
cols = list(tab)
print(f"{'metric':52s}" + "".join(f"{c:>17s}" for c in cols))
for k in list(next(iter(tab.values())).keys()):
    if k == "source": continue
    def f(v):
        if v is None: return "-"
        if isinstance(v, float): return f"{v:.6g}"
        return str(v)
    print(f"{k:52s}" + "".join(f"{f(tab[c][k]):>17s}" for c in cols))
