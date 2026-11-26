#!/bin/bash
# Agent 2: formal (EQY) classification of every mutant against the golden (D9: no exhaustive sim).
# RTL mutants at REGISTERED = 0 and 1; gate mutants at their own REGISTERED value.
# One EQY at a time. Writes equiv/classify/<name>/ and equiv/classification.json.
# EQY cannot see clock polarity, async-vs-sync reset timing within a cycle, latches vs flops
# (all are "a state element that updates"), init values or parameter defaults; those mutants are
# structural by design and are classified by MANIFEST class, not by EQY.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"; R="$HERE/.."
mkdir -p "$HERE/classify"
: > "$HERE/classify/summary.txt"
for f in "$R"/mutants/*.v; do
  n=$(basename "$f" .v)
  for r in 0 1; do
    "$HERE/run_eqy.sh" "$f" "classify/${n}_R$r" $r rtl | tee -a "$HERE/classify/summary.txt"
  done
done
for f in "$R"/gate_mutants/*.v; do
  n=$(basename "$f" .v)
  r=$(/usr/local/bin/python3 -c "import json,sys;print(json.load(open('$R/gate_mutants/MANIFEST.json'))['$n']['registered'])")
  "$HERE/run_eqy.sh" "$f" "classify/gate_${n}_R$r" $r gate | tee -a "$HERE/classify/summary.txt"
done
/usr/local/bin/python3 - "$HERE" <<'EOF'
import glob, json, os, sys
h = sys.argv[1]; out = {}
for p in sorted(glob.glob(os.path.join(h, "classify", "*", "result.json"))):
    r = json.load(open(p)); out[os.path.basename(os.path.dirname(p))] = r["result"]
json.dump(out, open(os.path.join(h, "classification.json"), "w"), indent=1)
print(len(out), "EQY classifications;", sum(v == "PASS" for v in out.values()), "PASS")
EOF
