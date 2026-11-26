#!/bin/bash
# verify.sh <cand.v> [eqy_tag]: provisional checks for a divider candidate (no frozen contract yet).
#  1. Verilator -Wall lint at (LATCH_DENOMINATOR, CHECK_INVALID) = (1,1) and (0,0).
#  2. EQY vs the immutable golden snapshot at P11 and P00: eqy_P11<tag>.eqy / eqy_P00<tag>.eqy
#     (default tag empty: SAT depth 1, flops matched by name, no assumptions).
#  3. Existing tests, unmodified, in a temp copy of the repo layout with src/divider.v = candidate:
#     test/divider/run.py (default params 1/1), test/controller/run.py (chip: 0/0).
set -u
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:$HOME/.local/bin:/opt/homebrew/bin:$PATH"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../../.." && pwd)"
C="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"; NAME=$(basename "$C" .v); TAG="${2:-}"
D="$HERE/runs/$NAME"; rm -rf "$D/eqy_P"* "$D/tests"; mkdir -p "$D/tests"
G="$HERE/../snapshot/divider.v"
T="$(mktemp -d "${TMPDIR:-/tmp}/dv_opt.XXXXXX")"
cp "$C" "$T/divider.v"
LINT=""
for P in 11 00; do
    (cd "$T" && verilator --lint-only -Wall -GLATCH_DENOMINATOR=${P:0:1} -GCHECK_INVALID=${P:1:1} --top-module divider divider.v > lint_P$P.log 2>&1; echo "rc=$?" >> lint_P$P.log)
    cp "$T/lint_P$P.log" "$D/"; LINT="$LINT P$P:$(tail -1 "$D/lint_P$P.log"),w=$(grep -c "^%Warning" "$D/lint_P$P.log")"
done
EQ=""
if [ "$TAG" = bridge ]; then
    # Re-encoded state: proof bridge (see bridge/make_bridge.py): golden == B, cand == C' (name-matched,
    # depth 1, no assumptions) and B == C' in the power-on-reset harness (SAT induction + SBY base case).
    python3 "$HERE/bridge/make_bridge.py" "$C" > /dev/null
    EQ="$("$HERE/bridge/run_side.sh" "$G" "$HERE/bridge/B_gold.v" B_gold | sed 's/^side //') $("$HERE/bridge/run_side.sh" "$C" "$HERE/bridge/C_$NAME.v" "C_$NAME" | sed 's/^side //')"
    for P in 11 00; do EQ="$EQ | $("$HERE/bridge/run_main.sh" "$C" $P)"; done
fi
for P in 11 00; do
    [ "$TAG" = bridge ] && break
    E="$T/e$P"; mkdir "$E"; cp "$G" "$E/gold.v"; cp "$C" "$E/gate.v"; cp "$HERE/eqy_P$P$TAG.eqy" "$E/eq.eqy"
    (cd "$E" && timeout 1800 /usr/local/bin/python3 "$HOME/.local/bin/eqy" -f eq.eqy > eqy.log 2>&1)
    mkdir -p "$D/eqy_P$P"; cp "$E/eqy.log" "$E/eq.eqy" "$D/eqy_P$P/"
    cp -R "$E/eq/partitions" "$D/eqy_P$P/" 2>/dev/null
    for s in "$E"/eq/strategies/*/*/run.log "$E"/eq/strategies/*/*/*/logfile.txt; do [ -f "$s" ] && { p=$(echo "$s" | sed "s|$E/eq/strategies/||; s|/|_|g"); cp "$s" "$D/eqy_P$P/$p"; }; done
    EQ="$EQ P$P:$(grep -o 'DONE ([A-Z]*' "$D/eqy_P$P/eqy.log" | tail -1 | tr -d '(' | sed 's/DONE //')/$(grep -c 'Successfully proved equivalence of partition' "$D/eqy_P$P/eqy.log")p"
done
# Tests: replicate repo layout (ROOT = parents[2] of run.py).
mkdir -p "$T/r/src" "$T/r/python"
cp -R "$ROOT/test" "$T/r/test"; rm -rf "$T/r/test/sim_build" "$T/r/test/blocks/sim_build"
cp -R "$ROOT/python/src" "$T/r/python/src"
cp "$ROOT"/pd_flow/baseline/original_rtl/* "$T/r/src/"; cp "$C" "$T/r/src/divider.v"
TS=""
for t in divider controller; do
    (cd "$T/r" && timeout 1200 /usr/local/bin/python3 test/$t/run.py > "$D/tests/$t.log" 2>&1; echo "rc=$?" >> "$D/tests/$t.log")
    TS="$TS $t:$(tail -1 "$D/tests/$t.log")"
done
rm -rf "$T"
echo "$NAME lint=[$LINT ] eqy=[$EQ ] tests=[$TS ]"
