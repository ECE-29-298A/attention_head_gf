#!/usr/bin/env python3
"""Build attempts.json from runs/ (candidates), runs/_noise (noise study), search/ and phase3_probe/."""
import json, os, re, glob, statistics as st, collections, hashlib, subprocess
H = os.path.dirname(os.path.abspath(__file__))
subprocess.run(["python3", os.path.join(H, "collect.py")], check=True, capture_output=True)
rows = json.load(open(os.path.join(H, "runs", "collected.json")))
g = next(r for r in rows if r["name"] == "golden")
TOL = 0.05  # "materially worse" timing: > 5 % longer worst a/b/cin->s path (N=22) at either corner

def netlist_area(d, w):
    t = open(os.path.join(d, f"netlist_n{w}.stat.txt")).read()
    return float(re.search(r"Chip area.*?:\s*([\d.]+)", t).group(1))

DESC = {
 "golden": "original hand-written ripple: s=a^b^c, c'=ab|c(a^b)",
 "c01_behavioural": "behavioural a + b + cin (cin zero-extended by generate); alumacc -> $alu",
 "c02_behav_cinfold": "behavioural {a,1}+{b,cin}, drop bit 0 (one (N+1)-bit add)",
 "c03_majority": "ripple, majority carry ab|ac|bc",
 "c04_mux_carry": "XOR-shared p=a^b, s=p^c, carry mux c'=p?c:a",
 "c05_inv_carry": "alternating-polarity ripple, inverting majority per stage",
 "c06_xnor_gp": "explicit g/p vectors, c'=g|p&c, s=p^c",
 "c06b_gp_fixed": "c06 with g only for carry-producing stages (lint-clean)",
 "c07_or_carry": "carry with OR propagate ab|(a|b)c",
 "c08_uniform_inv": "uniform inverted carry kn'=~((a|b)&~(~(ab)&kn)), s=~(a^b^kn)",
 "c09_alt_aoi22": "alternating polarity, aoi22/oai21-shaped carry",
 "c10_ab_or_c": "product-of-sums carry (a|b)&(ab|c)",
 "c11_mux_b": "carry mux c'=(a^b)?c:b",
 "c12_behav_assoc": "behavioural a + (b + cin)",
 "c14_sub_form": "behavioural a - ~b - (1-cin)",
 "c15_xor_prop_or": "golden form with shared p wire",
 "c16_maj_tuned": "majority carry, operand order = best of operand-order search (maj_4)",
 "c17_altmaj_tuned": "alternating-polarity majority, operand order = best of search (alt_maj_5)",
}
att = []
for r in rows:
    d = os.path.join(H, "runs", r["name"])
    a = {k: r[k] for k in r}
    a["description"] = DESC.get(r["name"], "")
    a["rtl"] = "baseline/original_rtl/ripple_add.v" if r["name"] == "golden" else f"opt/candidates/{r['name']}.v"
    src = os.path.join(H, "..", "..", "..", "baseline", "original_rtl", "ripple_add.v") if r["name"] == "golden" else os.path.join(H, "candidates", r["name"] + ".v")
    a["rtl_sha256"] = hashlib.sha256(open(src, "rb").read()).hexdigest()
    a["netlist_area_n22"] = netlist_area(d, 22); a["netlist_area_n12"] = netlist_area(d, 12)
    assert abs(a["netlist_area_n22"] - r["a22"]) < 1e-3 and abs(a["netlist_area_n12"] - r["a12"]) < 1e-3, r["name"]
    a["delta_vs_golden"] = {k: round(r[k] - g[k], 4) for k in ("a22", "a12", "mac", "top")}
    a["timing_delta_pct"] = {k: round(100 * (r[k] / g[k] - 1), 2) for k in ("t22_tt", "t22_ss", "t12_tt", "t12_ss")}
    reasons = []
    if r["name"] == "golden":
        a["decision"] = "reference (retained)"; att.append(a); continue
    if not r["contract_all_ok"]: reasons.append("contract not all ok: " + ",".join(r["contract_failed_items"]))
    if r["eqy_n12"] != "PASS" or r["eqy_n22"] != "PASS": reasons.append("EQY not proven")
    if not r["a22"] < g["a22"]: reasons.append(f"module area N=22 not lower ({r['a22']:.2f} vs {g['a22']:.2f})")
    if not r["a12"] < g["a12"]: reasons.append(f"module area N=12 not lower ({r['a12']:.2f} vs {g['a12']:.2f})")
    if not r["mac"] < g["mac"]: reasons.append("mac_unit area not lower")
    if not r["top"] < g["top"]: reasons.append("top area not lower")
    for k in ("t22_tt", "t22_ss"):
        if r[k] > g[k] * (1 + TOL): reasons.append(f"timing materially worse: {k} {r[k]:.3f} ns vs {g[k]:.3f} ns ({100*(r[k]/g[k]-1):+.1f}%)")
    a["decision"] = "accepted" if not reasons else "rejected"
    a["reasons"] = reasons
    att.append(a)

# noise study
def area_of(d):
    x = {y["module"]: y["area_um2"] for y in json.load(open(os.path.join(d, "area.json")))["results"]}
    return x["ripple_add_22"], x["ripple_add_12"], x["mac_unit"], x["tt_um_attention_head_gf"]
gold_fam = [("original",) + (g["a22"], g["a12"], g["mac"], g["top"])]
for d in sorted(glob.glob(os.path.join(H, "runs", "_noise", "[np]*"))):
    gold_fam.append((os.path.basename(d),) + area_of(d))
beh_fam = [(os.path.basename(d),) + area_of(d) for d in sorted(glob.glob(os.path.join(H, "runs", "_noise", "v0*")))]
def summ(f):
    out = {}
    for i, k in enumerate(("a22", "a12", "mac", "top"), 1):
        v = [x[i] for x in f]
        out[k] = {"min": min(v), "median": st.median(v), "max": max(v), "distinct": len(set(v))}
    return out
noise = {
 "purpose": "Functionally and structurally identical rewrites (renames, comment, operand order) of one formulation; measures ABC tie-break noise under the unchanged recipe.",
 "golden_family": {"variants": len(gold_fam), "summary": summ(gold_fam),
                   "rows": [dict(zip(("name", "a22", "a12", "mac", "top"), x)) for x in gold_fam]},
 "behavioural_family": {"variants": len(beh_fam), "summary": summ(beh_fam),
                        "rows": [dict(zip(("name", "a22", "a12", "mac", "top"), x)) for x in beh_fam]},
 "finding": "Module-level area is invariant within each family (deterministic). mac_unit and top-level area vary by up to ~700 and ~1150 um2 with operand order alone; the original's top area 42,145.64 is the maximum of its own family. Top-level deltas smaller than this band are not attributable to the adder.",
}
# search
search = {}
for fn in ("quick2.txt", "quick3.txt"):
    d = collections.defaultdict(dict)
    for l in open(os.path.join(H, "search", fn)):
        f, n, v = l.split(); d[f.rsplit(".", 1)[0]][n] = float(v)
    for k, v in d.items():
        fam = k.rsplit("_", 1)[0]
        search.setdefault(fam, []).append((v["N=22"], v["N=12"]))
ssum = {f: {"variants": len(v), "a22_min": min(x[0] for x in v), "a22_median": st.median(x[0] for x in v),
            "a12_min": min(x[1] for x in v), "a12_median": st.median(x[1] for x in v)} for f, v in search.items()}
screen = []
for dd in sorted(glob.glob(os.path.join(H, "search", "sta_screen", "*"))):
    rr = {"variant": os.path.basename(dd)}
    for c in ("tt_025C_3v30", "ss_125C_3v00"):
        m = re.search(r"worst_arrival_ns=([\d.]+)", open(os.path.join(dd, f"sta_n22_{c}.log")).read())
        rr["t22_" + c[:2]] = float(m.group(1))
    screen.append(rr)
probe = {}
for w in (22, 12):
    for c in ("tt_025C_3v30", "ss_125C_3v00"):
        m = re.search(r"worst_arrival_ns=([\d.]+)", open(os.path.join(H, "phase3_probe", f"sta_n{w}_{c}.log")).read())
        probe[f"t{w}_{c[:2]}"] = float(m.group(1))
probe.update({"area_n22": 22 * 72.4416, "area_n12": 12 * 72.4416,
              "gate_contract_n22": json.load(open(os.path.join(H, "phase3_probe", "gate_contract_n22", "results.json")))["all_ok"],
              "gate_contract_n12": json.load(open(os.path.join(H, "phase3_probe", "gate_contract_n12", "results.json")))["all_ok"],
              "note": "Hand-instantiated addf_1 chain, NOT a Phase 2 candidate (cell instantiation is Phase 3). Reference only."})
out = {
 "module": "ripple_add", "phase": 2, "agent": 3,
 "recipe": {"area": "pd_flow/scripts/synth_area.py (Yosys 0.71, synth -flatten, dfflibmap, default abc -liberty, GF180 7t TT 025C 3V30), unchanged; full copy of original_rtl with only ripple_add.v replaced",
            "netlists_for_sta": "verif/gate/synth_gf180.sh (same recipe, write_verilog -noattr); netlist areas checked equal to synth_area module areas",
            "sta": "OpenSTA 2.7.0 in librelane:3.0.14; opt/sta.tcl; input transition 0.30 ns on all inputs, 0.02 pF load on all outputs, virtual 100 ns clock, zero I/O delay, no wire load; Liberty tt_025C_3v30 and ss_125C_3v00",
            "eqy": "EQY SAT strategy depth 1 (complete for combinational logic), golden original vs candidate, N=12 and N=22, no assumptions/cutpoints/blackboxes (opt/eqy_template.eqy)",
            "contract": "verif/run_all.sh --rtl <cand> --out runs/<cand>/contract (frozen, hash b879560878477abf)"},
 "acceptance": "all contract items ok; EQY PASS at N=12 and N=22; module area lower at N=22 and N=12; mac_unit and top area lower than the original; worst N=22 path not more than 5% longer at TT and SS",
 "golden": {k: g[k] for k in ("a22", "a12", "mac", "top", "t22_tt", "t22_ss", "t12_tt", "t12_ss")},
 "attempts": att,
 "accepted": [a["name"] for a in att if a.get("decision") == "accepted"],
 "result": None,
 "noise_study": noise,
 "operand_order_search": {"families": ssum, "variants_smaller_than_golden_at_both_N": len(screen),
                          "sta_screen_n22": screen,
                          "finding": "Every search variant smaller than the original at both widths is at least 21.8% slower (TT, N=22)."},
 "phase3_probe_addf_chain": probe,
}
out["result"] = "original retained" if not out["accepted"] else "accepted: " + ",".join(out["accepted"])
json.dump(out, open(os.path.join(H, "attempts.json"), "w"), indent=1)
print(out["result"])
for a in att:
    print(a["name"], a["decision"], "; ".join(a.get("reasons", [])))
print(json.dumps(noise["golden_family"]["summary"])); print(json.dumps(noise["behavioural_family"]["summary"]))
print(json.dumps(ssum)); print(min(x["t22_tt"] for x in screen)); print(probe)
