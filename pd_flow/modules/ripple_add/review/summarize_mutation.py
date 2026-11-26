#!/usr/bin/env python3
"""Summarize the mutation runs into mutation_results.json (Agent 2 review).

Inputs: mutants/mutants.json, mutation_runs/<m>/results.json (Agent 1's contract applied to
the mutant), equiv/equiv_summary.txt (Agent 2's independent golden-vs-mutant miter).
A mutant is KILLED if any contract item has ok=false; the killing items are listed and
grouped by method. A survivor is EQUIVALENT only if the independent miter proved it equal
to the golden RTL at every instantiated N (12, 22) and the default (16); otherwise it is a
contract GAP.
"""
import json
import os
import sys

REV = os.path.dirname(os.path.abspath(__file__))


def group(iid):
    for p, g in (("fv_prove", "formal-prove"), ("fv_pdr", "formal-pdr"), ("fv_cover", "formal-cover"),
                 ("fv_sanity", "formal-negctl"), ("exh", "sim-exhaustive"), ("vec", "sim-vectors"),
                 ("rand", "sim-random"), ("lint", "static-lint/interface"), ("build", "build"),
                 ("selftest", "model-selftest")):
        if iid.startswith(p):
            return g
    return "other"


def main() -> int:
    meta = json.load(open(os.path.join(REV, "mutants", "mutants.json")))
    eq = {}
    for line in open(os.path.join(REV, "equiv", "equiv_summary.txt")):
        f = line.split()
        if f:
            eq[f[0]] = dict(zip(f[1::2], f[2::2]))
    golden = json.load(open(os.path.join(REV, "rerun_golden", "results.json")))
    out = []
    for m in meta:
        name = m["name"]
        p = os.path.join(REV, "mutation_runs", name, "results.json")
        rec = dict(m)
        rec["miter_golden_vs_mutant"] = eq.get(name, {})
        if not os.path.exists(p):
            rec.update(verdict="NOT-RUN", killed=False, killing_items=[])
            out.append(rec)
            continue
        r = json.load(open(p))
        bad = [i for i in r["items"] if not i["ok"]]
        groups = {}
        for i in bad:
            groups.setdefault(group(i["id"]), []).append(f'{i["id"]}:{i["status"]}')
        functional = sorted(g for g in groups if g.startswith(("formal-prove", "formal-pdr", "sim-")))
        rec.update(
            dut_sha256=r["dut_sha256"],
            items_ok=r["items_ok"], items_total=r["items_total"], all_ok=r["all_ok"],
            killed=not r["all_ok"],
            killing_items=[i["id"] for i in bad],
            killed_by_group={g: v for g, v in sorted(groups.items())},
            killed_by_functional_check=bool(functional),
            evidence=f"mutation_runs/{name}/results.json",
        )
        if rec["killed"]:
            rec["verdict"] = "KILLED"
        else:
            vals = rec["miter_golden_vs_mutant"]
            if vals and all(vals.get(t) == "PASS" for t in ("n12", "n16", "n22")):
                rec["verdict"] = "SURVIVED-EQUIVALENT"
            else:
                rec["verdict"] = "SURVIVED-GAP"
        out.append(rec)
    nonequiv = [r for r in out if not r["name"].startswith("e")]
    killed = [r for r in nonequiv if r["killed"]]
    res = {
        "module": "ripple_add",
        "contract": "pd_flow/modules/ripple_add/verif/run_all.sh (pristine copy: review/harness/verif_copy)",
        "golden_rerun_all_ok": golden["all_ok"],
        "golden_rerun_items": f'{golden["items_ok"]}/{golden["items_total"]}',
        "mutants_total": len(out),
        "non_equivalent_mutants": len(nonequiv),
        "killed": len(killed),
        "killed_by_functional_check": sum(r.get("killed_by_functional_check", False) for r in nonequiv),
        "survived_gap": [r["name"] for r in out if r.get("verdict") == "SURVIVED-GAP"],
        "survived_equivalent": [r["name"] for r in out if r.get("verdict") == "SURVIVED-EQUIVALENT"],
        "equivalent_wrongly_killed": [r["name"] for r in out if r["name"].startswith("e") and r["killed"]],
        "mutation_score": f"{len(killed)}/{len(nonequiv)}",
        "mutants": out,
    }
    json.dump(res, open(os.path.join(REV, "mutation_results.json"), "w"), indent=2)
    for r in out:
        g = r.get("killed_by_group", {})
        print(f'{r["name"]:<24} {r.get("verdict"):<20} {r.get("items_ok", "-")}/{r.get("items_total", "-")} '
              + " ".join(f"{k}({len(v)})" for k, v in g.items()))
    print("score", res["mutation_score"], "gaps", res["survived_gap"], "equiv", res["survived_equivalent"],
          "equiv-killed", res["equivalent_wrongly_killed"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
