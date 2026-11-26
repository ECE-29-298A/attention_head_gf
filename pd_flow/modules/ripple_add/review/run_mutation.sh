#!/bin/bash
# Agent 2 mutation run: applies Agent 1's unmodified contract (pristine copy in
# harness/verif_copy, hashes in harness/agent1_sources.sha256) to every mutant in mutants/.
# Each mutant runs in its own fresh copy of the contract in the scratch area, sequentially
# (run_all.sh itself uses 6 jobs; CPU budget 8). Per-mutant results.json and logs are copied
# to mutation_runs/<mutant>/. Then summarize_mutation.py writes mutation_results.json.
# Usage: run_mutation.sh [mutant-name ...]   (default: all mutants/*.v)
set -u
REV="$(cd "$(dirname "$0")" && pwd)"
SCR="${SCRATCH:-${TMPDIR:-/tmp}}/ripple_add_mut"
mkdir -p "$SCR" "$REV/mutation_runs"
if [ $# -gt 0 ]; then names="$*"; else names=$(cd "$REV/mutants" && ls *.v | sed 's/\.v$//'); fi
for m in $names; do
    w="$SCR/$m"; rm -rf "$w"; cp -R "$REV/harness/verif_copy" "$w"
    "$w/run_all.sh" --rtl "$REV/mutants/$m.v" --jobs 6 > "$w/run_all.out" 2>&1; rc=$?
    o="$REV/mutation_runs/$m"; rm -rf "$o"; mkdir -p "$o"
    cp "$w/results.json" "$w/run_all.out" "$o/" 2>/dev/null
    cp -R "$w/logs" "$o/logs" 2>/dev/null
    # keep the counterexample traces of failed formal tasks (small) as kill evidence
    for d in "$w"/formal/runs/*; do
        [ -d "$d" ] || continue
        st=$(awk '{print $1}' "$d/status" 2>/dev/null)
        if [ "$st" = FAIL ] && ! echo "$d" | grep -q sanity; then
            mkdir -p "$o/cex/$(basename "$d")"; cp "$d"/engine_0/trace*.vcd "$o/cex/$(basename "$d")/" 2>/dev/null
        fi
    done
    echo "$m rc=$rc $(tail -1 "$w/run_all.out")"
    rm -rf "$w"
done
