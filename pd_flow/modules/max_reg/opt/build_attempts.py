#!/usr/bin/env python3
"""build_attempts.py: runs/collected.json + decisions -> attempts.json."""
import json, os
H = os.path.dirname(os.path.abspath(__file__))
rows = {r["name"]: r for r in json.load(open(os.path.join(H, "runs", "collected.json")))}
hm = json.load(open(os.path.join(H, "harden_c10_clean", "metrics.json")))
bm = json.load(open(os.path.join(H, "../../../baseline/harden/metrics.json")))
D = {
 "c01_ge": ("rejected", "chip -2.2 um2: inside the noise band. The module-level -325 (reviewer: -272) is default-ABC noise; n06 (pure operand swap M < S_in) also shows -296 at module level."),
 "c02_not_mgt": ("rejected", "chip +241.5"),
 "c03_sub_sign_gt": ("rejected", "chip +241.5 (same netlist as c02 after Yosys canonicalisation)"),
 "c04_sub_sign_ge": ("rejected", "chip -166.8 but in-context max_reg logic +19.8: the gain is rest-of-chip ABC variation, not max_reg. Variant spread -226..+99 vs base (v4 +98.8)."),
 "c05_ob_gt": ("rejected", "chip -41.7: inside the noise band"),
 "c06_ob_ge": ("rejected", "chip +105.4"),
 "c07_carry_gt": ("rejected", "chip +173.4"),
 "c08_ripple_gt": ("rejected", "chip -127.3, but variants reach +805.6 (v3) and +368.8 (v4); dominated by c10"),
 "c09_ripple_ge": ("rejected", "chip -171.2, variants up to +384.2 (v4); dominated by c10 family on robustness"),
 "c10_ripple_dc": ("hardened (as c10_clean), then rejected", "best family: 4 of 5 distinct texts at -134..-180 chip, in-context max_reg -184..-246. The harden of its lowest text reversed the gain: std-cell +254.7 um2, setup WNS -1.57 ns, power +10.3%."),
 "c11_ripple_alt": ("rejected", "chip -147.1, variants up to +531.2 (v3); in-context logic same as c10"),
 "c12_muxchain": ("rejected", "smallest in-context logic (2697.9) but chip +138.3; variants -199.8..+309.5"),
 "c13_tree": ("rejected", "chip +256.8"),
 "c14_le_swap": ("rejected", "chip +419.3"),
 "c10_clean": ("hardened, then rejected; original retained", "the c10_v4 text with cleaned comments. Shipped-flow netlist is byte-identical to c10_v4 (40,936.0896, -180.0). Harden is worse than baseline and no better than the cosmetic-rewrite harden noise (ra_n03 46,990.5, ra_n04 47,220.9). Power is outside the noise band (3.365 vs 2.971..3.220 mW)."),
}
cands = []
for n, (dec, why) in D.items():
    r = dict(rows[n]); r["decision"] = dec; r["reason"] = why; cands.append(r)
cands.append({"name": "k01_drop_bit21", "kind": "context_only", "file": "context_only/k01_drop_bit21.v",
    "description": "21 flops; M[21] = M[20] & |M[19:0], which holds only for in-context scores in [-1,040,384, 2^20]",
    "module_area_synth_area": 3512.32, "top_area_synth_area": 42143.4496, "chip_area_shipped": 41357.568, "chip_cells_shipped": 1439,
    "chip_delta": 241.472, "eqy": "not run", "contract": "not run (fails standalone by design)",
    "decision": "rejected", "reason": "area probe only: module +151.5, chip +241.5. Rebuilding M[21] costs more than one dffq + mux. Not proven, because it was rejected on area."})
keys = ["design__instance__area__stdcell", "design__instance__utilization", "design__instance__count__stdcell",
        "timing__setup__ws", "timing__hold__ws", "timing__setup_vio__count", "timing__hold_vio__count",
        "design__max_slew_violation__count", "design__max_cap_violation__count", "design__max_fanout_violation__count",
        "power__total", "route__wirelength", "route__drc_errors", "antenna__violating__nets",
        "magic__drc_error__count", "magic__illegal_overlap__count", "design__lvs_error__count"]
keys += sorted(k for k in bm if k.startswith(("timing__setup__ws__corner", "timing__hold__ws__corner")))
out = {
 "module": "max_reg", "phase": 2, "agent": 3, "date": "2026-11-26",
 "golden": "pd_flow/baseline/original_rtl/max_reg.v (sha256 d7cdf381...)",
 "acceptance": "frozen contract all ok + EQY PASS vs golden (sat, depth 1, M matched by name, no assumptions/cutpoints/blackboxes) + shipped-flow chip area (ll_synth.sh) clearly below the noise band + one harden",
 "noise_study": {
   "method": "cosmetic / operand-order rewrites of the golden through ll_synth.sh (n01-n06, g_v1-g_v8); the same 8 transforms applied to the candidate families",
   "golden_distinct_chip_areas": sorted({rows[n]["chip_area_shipped"] for n in rows if n.startswith(("n0", "g_v", "c00"))}),
   "ripple_add_samples": [41100.7296, 41201.7088],
   "band": [41063.4112, 41350.9824],
   "notes": "n02, n04, g_v1, g_v7, g_v8 are byte-identical to the base netlist; g_v2 = n03; g_v4 = n05; g_v6 = g_v3 structure. The flow is deterministic: n01 (comment) and c10_clean (comments/renames) reproduce byte-identical netlists.",
   "harden_noise_samples_std_cell_um2": {"base": 46819.2, "ra_n03": 46990.5, "ra_n04": 47220.9},
   "harden_noise_samples_power_mW": {"base": 3.050, "ra_n03": 2.971, "ra_n04": 3.220}},
 "attempts": cands,
 "variants": [rows[n] for n in sorted(rows) if rows[n]["kind"] in ("variant", "noise")],
 "negative_controls": [rows[n] for n in sorted(rows) if rows[n]["kind"] == "negctl"],
 "harden": {"candidate": "c10_clean (= c10_v4 netlist)", "mirror": "/Users/samuelzhang/ttharden/mr_c10v4",
            "baseline": {k: bm.get(k) for k in keys}, "candidate_metrics": {k: hm.get(k) for k in keys},
            "power_nom_tt_rpt_W": {"baseline": {"seq": 1.114097e-03, "comb": 9.666996e-04, "clock": 3.891414e-04, "total": 2.469938e-03},
                                   "candidate": {"seq": 1.142972e-03, "comb": 1.196868e-03, "clock": 3.892200e-04, "total": 2.729061e-03}},
            "area_delta_by_class_um2": {"logic": -149.3, "buf": 241.5, "clkbuf": 74.6, "dly": 140.5, "clkinv": -52.7, "ff": 4.4, "inv": -4.4, "fill": -254.6}},
 "accepted": None,
 "result": "original retained: opt/best/max_reg.v is byte-identical to the golden",
}
json.dump(out, open(os.path.join(H, "attempts.json"), "w"), indent=1)
print("ok", len(cands), "attempts")
