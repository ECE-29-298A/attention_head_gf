#!/bin/bash
# run_side.sh <a.v> <b.v> <tag> : EQY a vs b at P11 and P00 with eqy_P<P>.eqy (SAT depth 1, flops and ports
# matched by name, no assumptions). Used for golden == B_gold and cand == C_cand (observers are extra ports).
set -u
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:$HOME/.local/bin:/opt/homebrew/bin:$PATH"
H="$(cd "$(dirname "$0")" && pwd)"; R=""
for P in 11 00; do
    T="$H/../runs/side_$3_P$P"; rm -rf "$T"; mkdir -p "$T"; cp "$1" "$T/gold.v"; cp "$2" "$T/gate.v"; cp "$H/eqy_side_P$P.eqy" "$T/eq.eqy"
    (cd "$T" && timeout 900 /usr/local/bin/python3 ~/.local/bin/eqy -f eq.eqy > eqy.log 2>&1)
    R="$R P$P:$(grep -o 'DONE ([A-Z]*' "$T/eqy.log" | tail -1 | tr -d '(' | sed 's/DONE //')/$(grep -c 'Successfully proved equivalence of partition' "$T/eqy.log")p,unmatched_warn=$(grep -ci 'warning' "$T/eqy.log")"
done
echo "side $3:$R"
