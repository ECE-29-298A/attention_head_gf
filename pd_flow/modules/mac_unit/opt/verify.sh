#!/bin/bash
# verify.sh <cand.v> [notests]: provisional checks for a mac_unit candidate (no frozen contract yet).
#  1. Verilator -Wall lint at OUTPUTS = 8, 4, 2 (candidate + snapshot ripple_add.v).
#  2. EQY vs the immutable golden snapshot at OUTPUTS = 8, 4, 2 (eqy_O.eqy.in: SAT depth 1, flops by name).
#  3. Existing tests, unmodified, in a temp copy of the repo layout with src/mac_unit.v = candidate:
#     test/blocks (make mac_unit at OUTPUTS 8, 4, 2), test/controller/run.py (8, 4, 2), test/top/run.py,
#     test/ (make -B, the TT cocotb test).
set -u
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:$HOME/.local/bin:/opt/homebrew/bin:$PATH"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../../.." && pwd)"
C="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"; NAME=$(basename "$C" .v)
D="$HERE/runs/$NAME"; rm -rf "$D/eqy_O"* "$D/tests" "$D/lint"*; mkdir -p "$D/tests"
G="$HERE/../snapshot"
T="$(mktemp -d "${TMPDIR:-/tmp}/mc_opt.XXXXXX")"
cp "$C" "$T/mac_unit.v"; cp "$G/ripple_add.v" "$T/"
LINT=""
for O in 8 4 2; do
    (cd "$T" && verilator --lint-only -Wall -GOUTPUTS=$O --top-module mac_unit mac_unit.v ripple_add.v > lint_O$O.log 2>&1; echo "rc=$?" >> lint_O$O.log)
    cp "$T/lint_O$O.log" "$D/"; LINT="$LINT O$O:$(tail -1 "$D/lint_O$O.log"),w=$(grep -c "^%Warning" "$D/lint_O$O.log")"
done
EQ=""
for O in 8 4 2; do
    E="$T/e$O"; mkdir "$E"; cp "$G/mac_unit.v" "$E/gold.v"; cp "$C" "$E/gate.v"; cp "$G/ripple_add.v" "$E/"
    sed "s/@O@/$O/g" "$HERE/eqy_O.eqy.in" > "$E/eq.eqy"
    (cd "$E" && timeout 1800 /usr/local/bin/python3 "$HOME/.local/bin/eqy" -f eq.eqy > eqy.log 2>&1)
    mkdir -p "$D/eqy_O$O"; cp "$E/eqy.log" "$E/eq.eqy" "$D/eqy_O$O/"
    cp -R "$E/eq/partitions" "$D/eqy_O$O/" 2>/dev/null
    EQ="$EQ O$O:$(grep -o 'DONE ([A-Z]*' "$D/eqy_O$O/eqy.log" | tail -1 | tr -d '(' | sed 's/DONE //')/$(grep -c 'Successfully proved equivalence of partition' "$D/eqy_O$O/eqy.log")p/$(grep -ci 'failed\|unknown' "$D/eqy_O$O/eqy.log")bad"
done
TS=""
if [ "${2:-}" != notests ]; then
    mkdir -p "$T/r/src" "$T/r/python"
    cp -R "$ROOT/test" "$T/r/test"; rm -rf "$T/r/test/sim_build" "$T/r/test/blocks/sim_build" "$T/r/test/results.xml" "$T/r/test/blocks/results.xml"
    cp -R "$ROOT/python/src" "$T/r/python/src"
    [ -f "$ROOT/info.yaml" ] && cp "$ROOT/info.yaml" "$T/r/"
    cp "$ROOT"/pd_flow/baseline/original_rtl/* "$T/r/src/"; cp "$C" "$T/r/src/mac_unit.v"
    for O in 8 4 2; do
        (cd "$T/r/test/blocks" && OUTPUTS=$O timeout 1200 make mac_unit > "$D/tests/blocks_O$O.log" 2>&1; rc=$?; grep -q "<failure" results.xml && rc=99; echo "rc=$rc" >> "$D/tests/blocks_O$O.log"; rm -f results.xml)
        TS="$TS blocks$O:$(tail -1 "$D/tests/blocks_O$O.log")"
    done
    (cd "$T/r" && timeout 1800 /usr/local/bin/python3 test/controller/run.py > "$D/tests/controller.log" 2>&1; echo "rc=$?" >> "$D/tests/controller.log")
    TS="$TS controller:$(tail -1 "$D/tests/controller.log")"
    (cd "$T/r" && timeout 1800 /usr/local/bin/python3 test/top/run.py > "$D/tests/top.log" 2>&1; echo "rc=$?" >> "$D/tests/top.log")
    TS="$TS top:$(tail -1 "$D/tests/top.log")"
    (cd "$T/r/test" && timeout 1800 make -B > "$D/tests/tt_make.log" 2>&1; rc=$?; grep -q "<failure" results.xml && rc=99; echo "rc=$rc" >> "$D/tests/tt_make.log")
    TS="$TS tt_make:$(tail -1 "$D/tests/tt_make.log")"
fi
rm -rf "$T"
echo "$NAME lint=[$LINT ] eqy=[$EQ ] tests=[$TS ]"
