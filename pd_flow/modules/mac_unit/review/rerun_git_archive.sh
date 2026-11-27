#!/bin/bash
# Agent 2: clean rerun of the COMMITTED contract (git archive HEAD of verif/ + snapshot/ into the
# scratchpad), golden RTL and both committed gate netlists plus my golden netlist, --jobs 2; then
# every RTL mutant, attack, gate mutant and gate attack through the same unmodified copy.
# Usage: rerun_git_archive.sh <scratch dir>
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../../../.." && pwd)"
S=$1; rm -rf "$S"; mkdir -p "$S"
( cd "$ROOT" && git archive HEAD pd_flow/modules/mac_unit/verif pd_flow/modules/mac_unit/snapshot ) | tar -x -C "$S"
V="$S/pd_flow/modules/mac_unit/verif"; R="$HERE/rerun"; mkdir -p "$R"
( cd "$ROOT" && git rev-parse HEAD ) > "$R/git_archive_commit.txt"
( cd "$S/pd_flow/modules/mac_unit" && find verif snapshot -type f -not -path '*/logs/*' -not -path '*/formal/runs/*' -not -name results.json -not -name run_all.console.log | sort | xargs shasum -a 256 ) > "$HERE/contract_hash_HEAD.txt"
"$V/run_all.sh" --jobs 2 > "$R/ga_rtl.console.txt" 2>&1; echo "rtl rc=$?"
mkdir -p "$R/ga_rtl"; cp "$V/results.json" "$R/ga_rtl/"
for n in "$V/gate/netlists/mac_unit_8_gf180.v:8" "$V/gate/netlists/mac_unit_2_gf180.v:2" "$HERE/gate_netlists/golden.v:8"; do f=${n%:*}; c=${n##*:}; b=$(basename "$f" .v)
  "$V/run_all.sh" --rtl "$f" --gate --config $c --out "$R/ga_gate_$b" --jobs 2 > "$R/ga_gate_$b.console.txt" 2>&1
  echo "gate $b rc=$?"
done
export CONTRACT_VERIF="$V"
/usr/local/bin/python3 "$HERE/run_mutants.py" "$HERE"/mutants/*.v > "$HERE/mutant_runs_rtl.console.txt" 2>&1
MANIFEST_DIR=attacks /usr/local/bin/python3 "$HERE/run_mutants.py" "$HERE"/attacks/*.v > "$HERE/mutant_runs_attacks.console.txt" 2>&1
/usr/local/bin/python3 "$HERE/run_mutants.py" --gate "$HERE"/gate_mutants/*.v > "$HERE/mutant_runs_gate.console.txt" 2>&1
MANIFEST_DIR=gate_attacks /usr/local/bin/python3 "$HERE/run_mutants.py" --gate "$HERE"/gate_attacks/*.v >> "$HERE/mutant_runs_gate.console.txt" 2>&1
echo ALL_DONE
