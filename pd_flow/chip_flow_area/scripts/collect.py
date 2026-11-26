#!/usr/bin/env python3
"""Collect every chip_flow_area run into results.json and print a comparison table.

usage: collect.py <out results.json>
Runs: the golden baseline (/Users/samuelzhang/ttharden/attention_head_gf/runs/wokwi) and every
/Users/samuelzhang/ttharden/fx_<tag> that has runs/wokwi. Deltas are against the baseline
(full runs) or against the p0_control partial run (partial runs; bit-identical to the baseline
through step 43).
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import summarize  # noqa: E402

ROOT = os.path.dirname(HERE)
H = "/Users/samuelzhang/ttharden"


def main():
    out = sys.argv[1]
    runs = {"baseline": f"{H}/attention_head_gf/runs/wokwi"}
    for d in sorted(glob.glob(f"{H}/fx_*/runs/wokwi")):
        runs[d.split("/fx_")[1].split("/")[0]] = d
    res = {}
    for tag, rd in runs.items():
        r = summarize.summarize(rd)
        fx = os.path.dirname(os.path.dirname(rd))
        ovr = os.path.join(ROOT, "overrides", f"{tag}.json")
        r["overrides"] = json.load(open(ovr)) if os.path.exists(ovr) else {}
        px = os.path.join(fx, "sta_proxy", "proxy.json")
        if os.path.exists(px):
            r["grt_sta_proxy"] = json.load(open(px))
        r.pop("grt_proxy", None)  # step-43 metrics: ss/ff entries are stale carry-overs
        syn = glob.glob(os.path.join(rd, "06-yosys-synthesis", "*.nl.v"))
        if syn:
            import hashlib
            r["synth_netlist_sha256"] = hashlib.sha256(open(syn[0], "rb").read()).hexdigest()
        res[tag] = r
    base = res["baseline"]["stdcell_um2"]
    ctrl = res.get("p0_control", res["baseline"])
    for tag, r in res.items():
        ref = res["baseline"] if r["kind"] == "full" else ctrl
        r["delta_stdcell_um2"] = round(r["stdcell_um2"] - ref["stdcell_um2"], 2)
        r["delta_ref"] = "baseline" if r["kind"] == "full" else "p0_control"
        r["delta_census_um2"] = {g: round(r["census_group_um2"].get(g, 0) - ref["census_group_um2"].get(g, 0), 1)
                                 for g in ref["census_group_um2"]}
    json.dump(res, open(out, "w"), indent=1)
    print(f"{'tag':22s} {'kind':9s} {'stdcell':>9s} {'delta':>7s}  {'cts':>7s} {'repair':>7s} {'logic':>7s}  "
          f"ss-slew(proxy) hold-ff(proxy) | signoff slew/cap/fo, setupWS, holdWS")
    for tag, r in res.items():
        dc = r["delta_census_um2"]
        px = r.get("grt_sta_proxy", {})
        ss = px.get("max_ss_125C_3v00", {})
        ff = px.get("max_ff_n40C_3v60", {})
        so = ""
        if r["kind"] == "full":
            so = f"{r['slew_vio']}/{r['cap_vio']}/{r['fanout_vio']}, {r['setup_ws_min']:.2f}, {r['hold_ws_min']:.3f}"
        print(f"{tag:22s} {r['kind'][:9]:9s} {r['stdcell_um2']:9.1f} {r['delta_stdcell_um2']:+7.1f}  "
              f"{dc.get('cts', 0):+7.1f} {dc.get('repair', 0):+7.1f} {dc.get('logic', 0):+7.1f}  "
              f"{str(ss.get('slew', '-')):>8s} {str(round(ff['hold_ws'], 3)) if ff else '-':>10s}     | {so}")


if __name__ == "__main__":
    main()
