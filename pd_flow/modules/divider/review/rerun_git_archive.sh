#!/bin/bash
# Agent 2: clean rerun of the COMMITTED contract (git archive HEAD of verif/, snapshot/, python/src
# into the scratchpad), golden RTL and the three committed gate netlists, --jobs 2; then every gate
# mutant through the same unmodified copy. Usage: rerun_git_archive.sh <scratch dir>
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(cd "$HERE/../../../.." && pwd)"
S=$1; rm -rf "$S"; mkdir -p "$S"
( cd "$ROOT" && git archive HEAD pd_flow/modules/divider/verif pd_flow/modules/divider/snapshot python/src ) | tar -x -C "$S"
V="$S/pd_flow/modules/divider/verif"; R="$HERE/rerun"; mkdir -p "$R"
( cd "$ROOT" && git rev-parse HEAD ) > "$R/git_archive_commit.txt"
"$V/run_all.sh" --jobs 2 > "$R/ga_rtl.console.txt" 2>&1; echo "rtl rc=$?"
mkdir -p "$R/ga_rtl"; cp "$V/results.json" "$R/ga_rtl/"
for n in divider_00_gf180:00 divider_11_gf180:11 divider_00_clkbuf_gf180:00; do f=${n%%:*}; c=${n##*:}
  "$V/run_all.sh" --rtl "$V/gate/netlists/$f.v" --gate --config $c --out "$R/ga_gate_$f" --jobs 2 > "$R/ga_gate_$f.console.txt" 2>&1
  echo "gate $f rc=$?"
done
CONTRACT_VERIF="$V" /usr/local/bin/python3 "$HERE/run_mutants.py" --gate "$HERE"/gate_mutants/*.v > "$HERE/mutant_runs_gate.console.txt" 2>&1
echo gate_mutants_done
