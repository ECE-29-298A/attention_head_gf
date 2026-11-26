#!/usr/bin/env python3
"""build_attempts.py: attempts.json from runs/collected.json (run collect.py first)."""
import json, os, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__))
rows = json.load(open(os.path.join(HERE, "runs", "collected.json")))
G = 41116.096; GEXP = 2447.648
DESC = {
 "c00_golden": "golden snapshot (radix-2 log shifter, 5-bit increment, 25-entry case, zeroing)",
 "c01_fold": "rounding folded into a 6-bit table indexed by floor(2D/2^shift)",
 "c02_sat": "golden datapath; overflow saturates the 5-bit index to 31 instead of zeroing W",
 "c03_fold_sat": "fold + overflow saturates the 6-bit window to 63",
 "c04_radix4": "radix-4 shifter (case on shift[3:2] then shift[1:0]), golden rounding",
 "c05_radix4_fold": "radix-4 shifter + folded table",
 "c06_fold_flat": "fold, 49 ungrouped case items",
 "c07_roundbit": "D>>shift window plus separately staged round-bit mux (no guard zero)",
 "c08_ormerge": "overflow don't-care: 15 shifter muxes replaced by hi | (!s & lo); golden rounding",
 "c09_ormerge_fold": "OR-merged shifter + folded table",
 "c10_ormerge_fold_sat3": "OR-merged shifter + folded table + 3-OR saturation (index >= 49 on overflow)",
 "c11_fold_sat3": "plain shifter + folded table + 3-OR saturation",
}
gold_by_v = {r["name"].replace("c00_golden", "") or "base": r for r in rows if r["family"] == "c00_golden"}
out = {"golden_chip_area": G, "golden_exp_incontext": GEXP,
       "noise_band_chip": {"golden_exp_lut_rewrites": sorted({r["chip_area"] for r in gold_by_v.values()}),
                           "max_reg_golden_rewrites_prior": [41063.4, 41076.6, 41116.1, 41197.3, 41348.8, 41351.0],
                           "combined": [41063.4, 41375.1296]},
       "labels": "eqy: proven (SAT, depth 1, no assumptions/cutpoints/blackboxes; R0 combinational, R1 same flop encoding); "
                 "blocks: existing cocotb test_exp_lut (pass-sampled); lint: pass-static. All provisional (no frozen contract).",
       "families": [], "texts": rows}
for fam in DESC:
    rs = [r for r in rows if r["family"] == fam]
    paired = {}
    for r in rs:
        v = r["name"].replace(fam, "") or "base"
        if v in gold_by_v and "chip_area" in r:
            paired[v] = round(r["chip_area"] - gold_by_v[v]["chip_area"], 1)
    ch = [r["chip_area"] for r in rs]; ex = [r["exp_incontext"] for r in rs]
    out["families"].append({
        "family": fam, "description": DESC[fam], "texts": len(rs),
        "all_verified": all(r.get("eqy_R0") == "PASS" and r.get("eqy_R1") == "PASS" and r.get("blocks") == "pass"
                            and r.get("lint_R0") == "rc=0" and r.get("lint_R1") == "rc=0" for r in rs),
        "synth_area_module_base": next(r.get("synth_area_module") for r in rs if r["name"] == fam),
        "ll_module_area_min_med_max": [min(r["ll_module_area"] for r in rs), st.median(r["ll_module_area"] for r in rs), max(r["ll_module_area"] for r in rs)],
        "chip_min_med_max": [min(ch), st.median(ch), max(ch)],
        "exp_incontext_min_med_max": [min(ex), st.median(ex), max(ex)],
        "paired_chip_delta_vs_golden_variant": paired,
        "decision": "retained (reference)" if fam == "c00_golden" else "rejected"})
json.dump(out, open(os.path.join(HERE, "attempts.json"), "w"), indent=1)
for f in out["families"]:
    print(f["family"], f["all_verified"], f["chip_min_med_max"], f["paired_chip_delta_vs_golden_variant"])
