#!/usr/bin/env python3
"""Agent 2 mutation driver for divider. Runs the FROZEN contract (verif/run_all.sh, unmodified)
on each mutant, one mutant at a time, and records which items killed it (ok == false).

Usage: run_mutants.py [--gate] [--extra "<args passed to run_all.sh>"] <mutant files...>
  RTL mutants:          review/mutants/*.v       -> review/mutation_runs/<name>/
  gate mutants (--gate): review/gate_mutants/*.v -> review/mutation_runs/gate_<name>/
Class/scope come from mutants/MANIFEST.json or gate_mutants/MANIFEST.json.
Results are merged into review/mutation_results.json (keyed by run name).
Agent 2 budget: --jobs 2 is always passed. Gate mutants get --config from the manifest.
"""
import json
import os
import shlex
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
VERIF = os.environ.get("CONTRACT_VERIF", os.path.join(HERE, "..", "verif"))  # a hash-checked copy may be used
RUNS = os.path.join(HERE, "mutation_runs")
RES = os.path.join(HERE, "mutation_results.json")


def first_comment(path):
    for line in open(path):
        if line.startswith("// mutant") or line.startswith("// gate mutant"):
            return line.split(":", 1)[1].strip()
    return ""


def main():
    args = sys.argv[1:]
    gate = "--gate" in args
    extra = []
    if "--extra" in args:
        i = args.index("--extra")
        extra = shlex.split(args[i + 1])
        del args[i:i + 2]
    files = [a for a in args if a != "--gate"]
    man = json.load(open(os.path.join(HERE, "gate_mutants" if gate else "mutants", "MANIFEST.json")))
    db = json.load(open(RES)) if os.path.exists(RES) else {"runs": {}}
    for f in files:
        name = os.path.splitext(os.path.basename(f))[0]
        key = ("gate_" if gate else "") + name
        out = os.path.join(RUNS, key)
        cmd = [os.path.join(VERIF, "run_all.sh")] + (["--gate"] if gate else []) + \
              ["--rtl", os.path.abspath(f), "--out", out] + extra
        if gate:
            cmd += ["--config", man[name]["config"]]
        if "--jobs" not in cmd:
            cmd += ["--jobs", "2"]      # Agent 2 budget
        t0 = time.time()
        p = subprocess.run(cmd, capture_output=True, text=True)
        os.makedirs(out, exist_ok=True)
        open(os.path.join(out, "driver.log"), "w").write(" ".join(cmd) + "\n" + p.stdout + p.stderr)
        rj = os.path.join(out, "results.json")
        entry = {"file": os.path.relpath(os.path.abspath(f), HERE), "mode": "gate" if gate else "rtl",
                 "description": first_comment(f), "class": man.get(name, {}).get("class", "?"),
                 "scope": man.get(name, {}).get("scope", man.get(name, {}).get("config", "?")),
                 "command": " ".join(os.path.relpath(c, HERE) if os.path.isabs(c) else c for c in cmd),
                 "contract_dir": VERIF, "run_all_rc": p.returncode, "seconds": round(time.time() - t0, 1)}
        if os.path.exists(rj):
            r = json.load(open(rj))
            items = r["items"]
            entry["items_ok"] = sum(1 for i in items if i["ok"])
            entry["items_total"] = len(items)
            # D9b contract: only items with gating = true decide (all_ok covers gating items only)
            g = [i for i in items if i.get("gating", True)]
            entry["items_ok"] = sum(1 for i in g if i["ok"])
            entry["items_total"] = len(g)
            entry["killed_by"] = [i["id"] for i in g if not i["ok"]]
            entry["killed_by_status"] = {i["id"]: i["status"] for i in g if not i["ok"]}
            entry["nongating_failed"] = [i["id"] for i in items if not i.get("gating", True) and not i["ok"]]
            entry["killed_by_formal"] = [x for x in entry["killed_by"] if x.startswith(("fv_", "eqy_"))]
            entry["killed_by_edge"] = [x for x in entry["killed_by"] if x.startswith("edge_")]
            entry["killed_by_static"] = [x for x in entry["killed_by"] if x.startswith(("lint", "build", "cells_prep", "gen", "selftest", "refcheck"))]
            entry["all_ok"] = r.get("all_ok")
            entry["outcome"] = "killed" if entry["killed_by"] else "survived"
        else:
            entry["outcome"] = "killed" if p.returncode else "survived"
            entry["killed_by"] = ["run_all (no results.json: " + ((p.stderr or p.stdout).strip().splitlines() or ["?"])[-1] + ")"]
        db["runs"][key] = entry
        json.dump(db, open(RES, "w"), indent=2)
        print(f"{key:<34} {entry['class']:<20} {entry['outcome']:<9} {entry.get('items_ok','-')}/{entry.get('items_total','-')} "
              f"{entry['seconds']:6.1f}s killed_by={','.join(entry['killed_by'])}", flush=True)


if __name__ == "__main__":
    main()
