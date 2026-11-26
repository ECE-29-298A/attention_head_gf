#!/usr/bin/env python3
"""Collect every min_drive run into results.json and print the comparison table.

usage: collect_md.py <out results.json>
Runs: h2 (reference full harden, /Users/samuelzhang/ttharden/fx_h2_k6) and every
/Users/samuelzhang/ttharden/md_<tag> with runs/wokwi. Deltas are against h2 at the same stage:
the std-cell area after step 43 equals the final area (EXPERIMENTS.md, h2), so partial runs are
compared with h2's final area; timing/slew of runs through step 55 are compared with h2 signoff.
"""
import glob
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
sys.path.insert(0, HERE)
import census  # noqa: E402
import summarize  # noqa: E402
import upsize_diff  # noqa: E402

T = "/Users/samuelzhang/ttharden"
OVR = os.path.join(HERE, "..", "overrides")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest() if p and os.path.exists(p) else None


def one(glob_pat):
    g = sorted(glob.glob(glob_pat))
    return g[0] if g else None


def failed_step(rd):
    """The step dir that has no state_out.json (the flow stopped there), else None."""
    for d in sorted((d for d in os.listdir(rd) if d[:2].isdigit()), key=lambda d: int(d.split("-")[0])):
        if not os.path.exists(os.path.join(rd, d, "state_out.json")):
            return d
    return None


def run_info(tag, rd):
    bad = failed_step(rd)
    if bad:
        err = open(os.path.join(rd, "error.log")).read().strip() if os.path.exists(os.path.join(rd, "error.log")) else ""
        o = os.path.join(OVR, f"{tag}.json")
        return {"run": rd, "error": f"flow stopped at {bad}: {err[:300]}",
                "synth_netlist_sha256": sha(one(os.path.join(rd, "06-yosys-synthesis", "*.nl.v"))),
                "overrides": json.load(open(o)) if os.path.exists(o) else None}
    r = summarize.summarize(rd)
    steps = sorted(d for d in os.listdir(rd) if d[:2].isdigit())
    r["last_step"] = steps[-1]
    syn = one(os.path.join(rd, "06-yosys-synthesis", "*.nl.v"))
    cts = one(os.path.join(rd, "35-openroad-cts", "*.nl.v"))
    rsz = one(os.path.join(rd, "32-openroad-repairdesignpostgpl", "*.nl.v"))
    r["synth_netlist_sha256"] = sha(syn)
    r["post_repair_netlist_sha256"] = sha(rsz)
    r["post_cts_netlist_sha256"] = sha(cts)
    if syn:
        c = census.census(syn)
        r["synth_um2"] = c["total_um2"]
        r["synth_cells"] = c["count"]
        r["synth_mux2"] = {k: v for k, v in c["by_master"].items() if k.startswith("mux2")}
        r["synth_by_master"] = c["by_master"]
    ref_nl = cts or rsz
    if syn and ref_nl:
        d = upsize_diff.diff(syn, ref_nl)
        r["resized_count"] = d["resized_count"]
        r["resized_um2"] = d["resized_um2"]
        r["resized_by_pair"] = d["resized_by_pair"]
        r["inserted_by_group_um2"] = d["inserted_by_group_um2"]
    log = one(os.path.join(rd, "32-openroad-repairdesignpostgpl", "openroad-*.log"))
    if log:
        t = open(log).read()
        g = lambda rx: (lambda m: int(m.group(1)) if m else None)(re.search(rx, t))
        r["rsz_log"] = {"slew_violations_found": g(r"RSZ-0034\] Found (\d+) slew"),
                        "fanout_violations_found": g(r"RSZ-0035\] Found (\d+) fanout"),
                        "resized": g(r"RSZ-0039\] Resized (\d+) instances"),
                        "buffers_inserted": g(r"RSZ-0038\] Inserted (\d+) buffers")}
    fx = os.path.dirname(os.path.dirname(rd))
    px = os.path.join(fx, "sta_proxy", "proxy.json")
    if os.path.exists(px):
        r["grt_sta_proxy"] = json.load(open(px))
    r.pop("grt_proxy", None)
    o = os.path.join(OVR, f"{tag}.json") if tag != "h2" else os.path.join(HERE, "..", "..", "overrides", "h2_k6.json")
    r["overrides"] = json.load(open(o)) if os.path.exists(o) else None
    if r["overrides"] and tag != "h2":
        x = r["overrides"].get("EXTRA_EXCLUDED_CELLS")
        if x:
            r["overrides"] = dict(r["overrides"], EXTRA_EXCLUDED_CELLS=f"{len(x)} cells (see overrides/{tag}.json)")
    return r


def main():
    out = sys.argv[1]
    runs = {"h2": f"{T}/fx_h2_k6/runs/wokwi"}
    for d in sorted(glob.glob(f"{T}/md_*/runs/wokwi")):
        tag = d.split("/md_")[1].split("/")[0]
        if glob.glob(os.path.join(d, "06-yosys-synthesis", "*.nl.v")):
            runs[tag] = d
    res = {}
    for tag, rd in runs.items():
        try:
            res[tag] = run_info(tag, rd)
        except Exception as e:  # a run that could not be summarized
            res[tag] = {"run": rd, "error": repr(e)}
    h2 = res["h2"]
    for tag, r in res.items():
        if "stdcell_um2" not in r or r["stdcell_um2"] is None:
            continue
        r["delta_vs_h2_um2"] = round(r["stdcell_um2"] - h2["stdcell_um2"], 2)
        r["delta_census_vs_h2_um2"] = {g: round(r["census_group_um2"].get(g, 0) - h2["census_group_um2"].get(g, 0), 1)
                                       for g in sorted(set(h2["census_group_um2"]) | set(r["census_group_um2"]))}
        r["delta_class_vs_h2_um2"] = {c: round((r["class_um2"].get(c) or 0) - (h2["class_um2"].get(c) or 0), 1)
                                      for c in h2["class_um2"]}
        if r.get("synth_um2") is not None:
            r["delta_synth_vs_h2_um2"] = round(r["synth_um2"] - h2["synth_um2"], 3)
    # experiment-2 evidence (mux2_1 DRC) and run metadata
    md = os.path.join(HERE, "..")
    drc = os.path.join(md, "drc", "drc_summary.json")
    tbm = os.path.join(md, "drc", "tblock", "metrics.json")
    meta = {
        "reference": "h2 = chip_flow_area h2_k6 full harden (/Users/samuelzhang/ttharden/fx_h2_k6)",
        "tools": {"librelane": "3.0.14 (ghcr.io/librelane/librelane:3.0.14)", "openroad": "dcf36133",
                  "yosys": "0.62", "magic": "8.3.623", "klayout_docker": "0.30.7", "klayout_host": "0.30.14"},
        "pdk_harden": "gf180mcuD open_pdks 54435919abffb937387ec956209f9cf5fd2dfbee",
        "pdk_tt_precheck": "gf180mcuD e8daeda73ca8f5814dbc0b11d1d05802251a3750 (tt-gds-action@ttgf26c)",
        "partial_vs_full": "x0_mux21 (--to OpenROAD.STAPostPNR) and x0_full (tt_tool --harden) are bit-identical: "
                           "synthesis, post-CTS, routed netlist, DEF, SPEF (apart from *DATE)",
        "full_hardens_used": ["x0_full"],
        "d2_band": {"slew": 381, "cap": 2, "fanout": 13},
    }
    res = {"_meta": meta, **res}
    if os.path.exists(drc):
        res["_mux2_1_drc"] = json.load(open(drc))
    if os.path.exists(tbm):
        m = json.load(open(tbm))
        keep = ("magic__drc_error__count", "design__lvs_error__count", "antenna__violating__nets",
                "route__drc_errors", "design__instance__count__stdcell", "timing__hold__ws", "timing__setup__ws")
        res["_mux2_1_test_block"] = {"design": "mux2_drc_block (drc/tblock/src), 80 mux2_1 (64 instantiated + 16 mapped)",
                                     **{k: m.get(k) for k in keep}}
    json.dump(res, open(out, "w"), indent=1)
    print(f"{'tag':16s} {'step':28s} {'stdcell':>9s} {'d_h2':>7s} {'d_syn':>7s} {'logic':>7s} {'repair':>7s} {'cts':>7s} "
          f"{'rsz#':>4s} {'buf#':>4s}  slew/cap/fo  setupWS  holdWS")
    for tag, r in res.items():
        if tag.startswith("_"):
            continue
        if "delta_vs_h2_um2" not in r:
            print(f"{tag:16s} {r.get('error', '')[:80]}")
            continue
        dc = r["delta_census_vs_h2_um2"]
        so = ""
        if r["kind"] == "full" or "stapostpnr" in r["last_step"]:
            so = f"{r['slew_vio']}/{r['cap_vio']}/{r['fanout_vio']}  {r['setup_ws_min']:.2f}  {r['hold_ws_min']:.3f}"
        elif r.get("grt_sta_proxy"):
            p = r["grt_sta_proxy"]
            so = f"proxy {p['max_ss_125C_3v00']['slew']}/{p['max_ss_125C_3v00']['cap']}/{p['max_ss_125C_3v00']['fanout']}  " \
                 f"{p['max_ss_125C_3v00']['setup_ws']:.2f}  {p['max_ff_n40C_3v60']['hold_ws']:.3f}"
        rl = r.get("rsz_log", {})
        print(f"{tag:16s} {r['last_step'][:28]:28s} {r['stdcell_um2']:9.1f} {r['delta_vs_h2_um2']:+7.1f} "
              f"{r.get('delta_synth_vs_h2_um2', 0):+7.1f} {dc.get('logic', 0):+7.1f} {dc.get('repair', 0):+7.1f} "
              f"{dc.get('cts', 0):+7.1f} {str(rl.get('resized')):>4s} {str(rl.get('buffers_inserted')):>4s}  {so}")


if __name__ == "__main__":
    main()
