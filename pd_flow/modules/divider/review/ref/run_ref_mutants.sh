#!/bin/bash
# Agent 2: every RTL mutant through the independent reference (div_spec.sv, WB lemmas, k-induction
# depth 2) at configs 00 and 11. PASS = the mutant is PROVEN to meet the specification (independent
# equivalence evidence for expected survivors). UNKNOWN/FAIL = not proven; a basecase FAIL is a
# counterexample within 2 steps, otherwise the failing induction assertion names the broken property
# (not a behavioural counterexample by itself). Lemma-guided BMC (depth 30) was tried and is too slow
# with z3 (>3 min per step at step 5), so behavioural kills are taken from the contract only.
# One SBY at a time (2 solver processes). Output: ref/mutant_ref_results.txt
cd "$(dirname "$0")/.."
: > ref/mutant_ref_results.txt
for f in mutants/*.v; do n=$(basename "$f" .v)
  for c in 00 11; do l=${c:0:1}; k=${c:1:1}
    r=$(ref/run_ref.sh "$f" "ref/runs/mut_${n}_$c" $l $k prove 2)
    base=$(grep -o "returned [a-zA-Z]* for basecase" "ref/runs/mut_${n}_$c/sby.log" | head -1)
    fa=$(grep -o "failed assertion div_spec\.[a-z_0-9]*" "ref/runs/mut_${n}_$c/sby.log" | sed 's/failed assertion div_spec\.//' | sort -u | tr '\n' ',')
    echo "$n $c ${r%% *} [$base] $fa" >> ref/mutant_ref_results.txt
  done
done
