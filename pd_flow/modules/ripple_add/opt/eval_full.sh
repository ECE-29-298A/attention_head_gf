#!/bin/bash
# eval_full.sh <cand.v>: frozen contract, EQY vs golden (N=12, 22), area at 4 levels,
# mapped netlists (N=22, N=12) for STA. Results under runs/<name>/.
set -u
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:$HOME/.local/bin:/opt/homebrew/bin:$PATH"
HERE="$(cd "$(dirname "$0")" && pwd)"
C="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"; NAME=$(basename "$C" .v)
D="$HERE/runs/$NAME"; mkdir -p "$D"
G="$HERE/../../../baseline/original_rtl/ripple_add.v"
# 1. lint (standalone Verilator -Wall at N=22, 12) + frozen contract
for n in 22 12; do verilator --lint-only -Wall -GN=$n --top-module ripple_add "$C" > "$D/lint_n$n.log" 2>&1; echo "rc=$?" >> "$D/lint_n$n.log"; done
"$HERE/../verif/run_all.sh" --rtl "$C" --out "$D/contract" > "$D/contract.console.log" 2>&1; CRC=$?
# 2. EQY golden vs candidate, SAT strategy, no assumptions/cutpoints/blackboxes
mkdir -p "$D/eqy"
for n in 12 22; do
    W="$(mktemp -d "${TMPDIR:-/tmp}/ra_eqy.XXXXXX")"
    cp "$G" "$W/golden.v"; cp "$C" "$W/dut.v"
    sed "s/@N@/$n/g" "$HERE/eqy_template.eqy" > "$W/eq.eqy"
    (cd "$W" && timeout 600 /usr/local/bin/python3 "$HOME/.local/bin/eqy" -f eq.eqy > eqy.log 2>&1)
    cp "$W/eqy.log" "$D/eqy/eqy_n$n.log"; cp "$W/eq.eqy" "$D/eqy/eq_n$n.eqy"; rm -rf "$W"
done
# 3. area (unchanged synth_area.py recipe, full RTL copy with only ripple_add.v replaced)
"$HERE/area_eval.sh" "$C" > /dev/null
# 4. mapped netlists with the same recipe (verif/gate/synth_gf180.sh) for STA
for n in 22 12; do "$HERE/../verif/gate/synth_gf180.sh" $n "$D/netlist_n$n.v" "$C" > "$D/netlist_n$n.log" 2>&1; done
echo "$NAME contract_rc=$CRC $(tail -1 "$D/contract.console.log") eqy12=$(grep -o 'DONE ([A-Z]*' "$D/eqy/eqy_n12.log" | tail -1) eqy22=$(grep -o 'DONE ([A-Z]*' "$D/eqy/eqy_n22.log" | tail -1)"
