#!/usr/bin/env python3
"""Summarize a chip_flow_area run (partial or full).

usage: summarize.py <runs/wokwi dir> [--json out.json]
Reads the last step's state_out.json metrics (final/metrics.json for a full run) and the
census of the latest netlist. Prints std-cell area by class, every-corner setup/hold WS,
slew/cap/fanout counts, power, DRC/LVS/antenna (full runs only).
"""
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CLS = ["sequential_cell", "multi_input_combinational_cell", "inverter", "buffer", "clock_buffer",
       "clock_inverter", "timing_repair_buffer", "tap_cell", "endcap_cell", "tie_cell"]


def load(rd):
    fm = os.path.join(rd, "final", "metrics.json")
    if os.path.exists(fm) and glob.glob(os.path.join(rd, "*-checker-lvs")):
        return json.load(open(fm)), "full", glob.glob(os.path.join(rd, "final", "nl", "*.nl.v"))[0]
    steps = sorted(d for d in os.listdir(rd) if d[:2].isdigit())
    m, last_nl = {}, None
    for s in steps:
        p = os.path.join(rd, s, "state_out.json")
        if os.path.exists(p):
            m = json.load(open(p))["metrics"] or m
        nl = glob.glob(os.path.join(rd, s, "*.nl.v"))
        if nl:
            last_nl = nl[0]
    return m, "partial:" + steps[-1], last_nl


def summarize(rd):
    m, kind, nl = load(rd)
    g = lambda k: m.get(k)
    r = {"run": rd, "kind": kind, "netlist": nl,
         "stdcell_um2": g("design__instance__area__stdcell"),
         "count_stdcell": g("design__instance__count__stdcell"),
         "utilization": g("design__instance__utilization"),
         "class_um2": {c: g(f"design__instance__area__class:{c}") for c in CLS}}
    corners = sorted({k.split("corner:")[1] for k in m if "corner:" in k and k.startswith("timing__setup__ws")})
    r["setup_ws"] = {c: g(f"timing__setup__ws__corner:{c}") for c in corners}
    r["hold_ws"] = {c: g(f"timing__hold__ws__corner:{c}") for c in corners}
    r["setup_ws_min"] = g("timing__setup__ws")
    r["hold_ws_min"] = g("timing__hold__ws")
    r["setup_vio"] = g("timing__setup_vio__count")
    r["hold_vio"] = g("timing__hold_vio__count")
    r["slew_vio"] = g("design__max_slew_violation__count")
    r["cap_vio"] = g("design__max_cap_violation__count")
    r["fanout_vio"] = g("design__max_fanout_violation__count")
    r["power_total_W"] = g("power__total")
    r["route_drc"] = g("route__drc_errors")
    r["magic_drc"] = g("magic__drc_error__count")
    r["lvs_errors"] = g("design__lvs_error__count")
    r["antenna_nets"] = g("antenna__violating__nets")
    r["route_antenna"] = g("route__antenna_violation__count")
    r["wirelength_um"] = g("route__wirelength")
    r["hold_buffers"] = g("design__instance__count__hold_buffer")
    p3 = glob.glob(os.path.join(rd, "*-openroad-stamidpnr-3", "state_out.json"))
    if p3:
        mm = json.load(open(p3[0]))["metrics"]
        r["grt_proxy"] = {k.split("corner:")[1] + ":" + k.split("__")[1].replace("max_", "").replace("_violation", ""): v
                          for k, v in mm.items() if "violation__count__corner" in k}
        r["grt_proxy"].update({"setup_ws:" + k.split("corner:")[1]: round(v, 3) for k, v in mm.items() if k.startswith("timing__setup__ws__corner")})
        r["grt_proxy"].update({"hold_ws:" + k.split("corner:")[1]: round(v, 3) for k, v in mm.items() if k.startswith("timing__hold__ws__corner")})
    if nl:
        sys.path.insert(0, HERE)
        import census
        c = census.census(nl)
        r["census_group_um2"] = c["by_group_um2"]
        r["census_cts"] = c["by_group_master"].get("cts", {})
        r["census_repair"] = c["by_group_master"].get("repair", {})
    return r


def main():
    rd = sys.argv[1]
    r = summarize(rd)
    if "--json" in sys.argv:
        json.dump(r, open(sys.argv[sys.argv.index("--json") + 1], "w"), indent=1)
    print(f"{r['kind']}  stdcell {r['stdcell_um2']}  cells {r['count_stdcell']}  util {r['utilization']}")
    print("  class:", {k: round(v, 1) for k, v in r["class_um2"].items() if v is not None})
    print("  census:", r.get("census_group_um2"))
    print("  cts:", r.get("census_cts"))
    print("  repair:", r.get("census_repair"))
    f = lambda d: {k.replace("_3v00", "").replace("_3v60", "").replace("_3v30", ""): (round(v, 3) if v is not None else None) for k, v in d.items()}
    print("  setup ws:", f(r["setup_ws"]))
    print("  hold ws:", f(r["hold_ws"]))
    print(f"  setup/hold vio {r['setup_vio']}/{r['hold_vio']}  slew/cap/fanout {r['slew_vio']}/{r['cap_vio']}/{r['fanout_vio']}"
          f"  power {r['power_total_W']}  drc {r['route_drc']}/{r['magic_drc']} lvs {r['lvs_errors']} ant {r['antenna_nets']}"
          f"  wl {r['wirelength_um']} holdbuf {r['hold_buffers']}")
    if r.get("grt_proxy"):
        print("  GRT-parasitic proxy (step 43):", r["grt_proxy"])


if __name__ == "__main__":
    main()
