#!/usr/bin/env python3
"""compare_runs.py <out.json> <label>=<run_root> ... -- signoff/area metrics of finished hardens
(<run_root>/runs/wokwi/final/metrics.json) side by side: std-cell area by class (the flow's classes;
note a repair buffer kept in a fed netlist is classed "buffer", not "timing_repair_buffer"), counts,
DRC/LVS/antenna, routed wire, slew/cap/fanout, setup/hold WS, utilization."""
import json, sys
KEYS = ["design__instance__area__stdcell", "design__instance__count__stdcell", "design__instance__utilization",
        "magic__drc_error__count", "design__lvs_error__count", "antenna__violating__nets", "route__drc_errors",
        "route__wirelength", "design__max_slew_violation__count", "design__max_cap_violation__count",
        "design__max_fanout_violation__count", "timing__setup__ws", "timing__hold__ws", "timing__setup_vio__count",
        "timing__hold_vio__count", "design__disconnected_pin__count"]
out = {}
for spec in sys.argv[2:]:
    lab, run = spec.split("=", 1)
    m = json.load(open(f"{run}/runs/wokwi/final/metrics.json"))
    d = {k: m.get(k) for k in KEYS}
    d["area_class"] = {k.split(":", 1)[1]: round(v, 1) for k, v in m.items() if k.startswith("design__instance__area__class:")}
    d["count_class"] = {k.split(":", 1)[1]: v for k, v in m.items() if k.startswith("design__instance__count__class:")}
    out[lab] = {"run": run, **d}
json.dump(out, open(sys.argv[1], "w"), indent=1)
labs = list(out)
for k in KEYS:
    print(f"{k:42s}", " ".join(f"{str(round(out[l][k], 3) if isinstance(out[l][k], float) else out[l][k]):>12s}" for l in labs))
for c in sorted({c for l in labs for c in out[l]["area_class"]}):
    print(f"{'area:' + c:42s}", " ".join(f"{out[l]['area_class'].get(c, 0):>12}" for l in labs))
for c in sorted({c for l in labs for c in out[l]["count_class"]}):
    print(f"{'count:' + c:42s}", " ".join(f"{out[l]['count_class'].get(c, 0):>12}" for l in labs))
