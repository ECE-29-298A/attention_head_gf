#!/usr/bin/env python3
"""Agent 2 mutation driver for max_reg. Runs the FROZEN contract (verif/run_all.sh, unmodified)
on each mutant, one mutant at a time (run_all.sh itself uses --jobs 6, within the 8-job budget),
and collects which items killed it (ok == false).

Usage: run_mutants.py [--gate] <mutant files...>
  RTL mutants: review/mutants/*.v            -> review/mutation_runs/<name>/
  gate mutants (--gate): review/gate_mutants/*.v -> review/mutation_runs/gate_<name>/
Results are merged into review/mutation_results.json (keyed by run name).
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
VERIF = os.path.join(HERE, "..", "verif")
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
    files = [a for a in args if a != "--gate"]
    db = json.load(open(RES)) if os.path.exists(RES) else {"runs": {}}
    for f in files:
        name = os.path.splitext(os.path.basename(f))[0]
        key = ("gate_" if gate else "") + name
        out = os.path.join(RUNS, key)
        cmd = [os.path.join(VERIF, "run_all.sh"), "--rtl", os.path.abspath(f), "--out", out, "--jobs", "6"]
        if gate:
            cmd.insert(1, "--gate")
        t0 = time.time()
        p = subprocess.run(cmd, capture_output=True, text=True)
        os.makedirs(out, exist_ok=True)
        open(os.path.join(out, "driver.log"), "w").write(p.stdout + p.stderr)
        rj = os.path.join(out, "results.json")
        entry = {"file": os.path.relpath(os.path.abspath(f), HERE), "mode": "gate" if gate else "rtl",
                 "description": first_comment(f), "run_all_rc": p.returncode,
                 "seconds": round(time.time() - t0, 1)}
        if os.path.exists(rj):
            r = json.load(open(rj))
            entry["items_ok"] = r["items_ok"]
            entry["items_total"] = r["items_total"]
            entry["killed_by"] = [i["id"] for i in r["items"] if not i["ok"]]
            entry["killed_by_status"] = {i["id"]: i["status"] for i in r["items"] if not i["ok"]}
            entry["outcome"] = "killed" if entry["killed_by"] else "survived"
        else:
            entry["outcome"] = "killed" if p.returncode else "survived"
            entry["killed_by"] = ["run_all (no results.json: " + (p.stderr.strip().splitlines() or ["?"])[-1] + ")"]
        db["runs"][key] = entry
        json.dump(db, open(RES, "w"), indent=2)
        print(f"{key:<28} {entry['outcome']:<9} {entry.get('items_ok','-')}/{entry.get('items_total','-')} "
              f"{entry['seconds']:6.1f}s killed_by={','.join(entry['killed_by'])}", flush=True)


if __name__ == "__main__":
    main()
