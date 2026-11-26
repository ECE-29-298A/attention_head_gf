#!/bin/bash
# run_main.sh <cand.v> <P> [basedepth]: bridge proof B vs C' at parameter set P (11|00).
#   induction: eqy_main_P<P>.eqy (Yosys SAT k-induction depth 2) -> must PASS
#   base case: eqy_base_P<P>.eqy (SBY smtbmc z3, xprop on, BMC from boot=1) -> basecase must pass
# Proven (unbounded, after power-on reset) iff both hold and base depth >= induction depth.
set -u
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:$HOME/.local/bin:/opt/homebrew/bin:$PATH"
H="$(cd "$(dirname "$0")" && pwd)"; n=$(basename "$1" .v); P=$2; BD=${3:-3}
R=""
for k in main base; do
    T="$H/../runs/$n/bridge_${k}_P$P"; rm -rf "$T"; mkdir -p "$T"
    cp "$H/B_gold.v" "$T/gold.v"; cp "$H/C_$n.v" "$T/gate.v"; cp "$H/eqtop_obs.v" "$T/"
    sed "s/^depth 3$/depth $BD/" "$H/eqy_${k}_P$P.eqy" > "$T/eq.eqy"
    (cd "$T" && timeout 2400 /usr/local/bin/python3 ~/.local/bin/eqy -f eq.eqy > eqy.log 2>&1)
    [ -n "${KEEPVCD:-}" ] || find "$T/eq/strategies" -name "*.vcd" -delete 2>/dev/null
    if [ $k = main ]; then
        R="$R induction=$(grep -o 'DONE ([A-Z]*' "$T/eqy.log" | tail -1 | tr -d '(' | sed 's/DONE //')"
    else
        R="$R basecase=$(grep -ho 'returned [a-zA-Z]* for basecase' "$T"/eq/strategies/*/sby/*/logfile.txt | awk '{print $2}')$(grep -ho 'returned FAIL$' "$T"/eq/strategies/*/sby/*/logfile.txt | head -1 | sed 's/returned /(bmc:/; s/$/)/')/d$BD"
    fi
done
echo "$n P$P:$R"
