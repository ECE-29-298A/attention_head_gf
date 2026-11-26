#!/bin/bash
# verify.sh <cand.v>: provisional checks for an exp_lut candidate (no frozen contract yet).
#  1. Verilator -Wall lint as exp_lut.v, at REGISTERED=0 and REGISTERED=1.
#  2. EQY vs the immutable golden snapshot, REGISTERED=0 (instantiated) and REGISTERED=1
#     (SAT, depth 1; no assumptions, cutpoints or black boxes).
#  3. The existing cocotb block test test/blocks/test_exp_lut.py (copied, unmodified), with
#     SRC_DIR pointing at the candidate; fails if results.xml has any <failure.
# Results: runs/<name>/{lint_R*.log,eqy_R*/,blocks/}; one summary line on stdout.
set -u
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:$HOME/.local/bin:/opt/homebrew/bin:$PATH"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../../.." && pwd)"
C="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"; NAME=$(basename "$C" .v)
D="$HERE/runs/$NAME"; rm -rf "$D/eqy_R0" "$D/eqy_R1" "$D/blocks"; mkdir -p "$D"
G="$HERE/../snapshot/exp_lut.v"
T="$(mktemp -d "${TMPDIR:-/tmp}/el_opt.XXXXXX")"
cp "$C" "$T/exp_lut.v"
LINT=""
for R in 0 1; do
    (cd "$T" && verilator --lint-only -Wall -GREGISTERED=$R --top-module exp_lut exp_lut.v > lint_R$R.log 2>&1; echo "rc=$?" >> lint_R$R.log)
    cp "$T/lint_R$R.log" "$D/"; LINT="$LINT R$R:$(tail -1 "$D/lint_R$R.log")"
done
EQ=""
for R in 0 1; do
    mkdir "$T/e$R"; cp "$G" "$T/e$R/gold.v"; cp "$C" "$T/e$R/gate.v"; cp "$HERE/eqy_R$R.eqy" "$T/e$R/eq.eqy"
    (cd "$T/e$R" && timeout 900 /usr/local/bin/python3 "$HOME/.local/bin/eqy" -f eq.eqy > eqy.log 2>&1)
    mkdir -p "$D/eqy_R$R"; cp "$T/e$R/eqy.log" "$T/e$R/eq.eqy" "$D/eqy_R$R/"
    cp -R "$T/e$R/eq/partitions" "$D/eqy_R$R/" 2>/dev/null
    EQ="$EQ R$R:$(grep -o 'DONE ([A-Z]*' "$D/eqy_R$R/eqy.log" | tail -1 | tr -d '(' | sed 's/DONE //')/$(grep -c 'Successfully proved equivalence of partition' "$D/eqy_R$R/eqy.log")p"
done
# The block Makefile cannot handle the space in the project path: run it in the temp dir.
B="$T/blocks"; mkdir -p "$B/src" "$D/blocks"
cp "$C" "$B/src/exp_lut.v"; cp "$ROOT/pd_flow/baseline/original_rtl/ripple_add.v" "$B/src/"
cp "$ROOT/test/blocks/Makefile" "$ROOT/test/blocks/test_exp_lut.py" "$B/"
(cd "$B" && make exp_lut SRC_DIR="$B/src" > make.log 2>&1); BRC=$?
cp "$B/make.log" "$D/blocks/"; cp "$B/results.xml" "$D/blocks/" 2>/dev/null
if [ $BRC -eq 0 ] && [ -f "$D/blocks/results.xml" ] && ! grep -q "<failure" "$D/blocks/results.xml" && grep -q "testcase" "$D/blocks/results.xml"; then BT=pass; else BT=FAIL; fi
rm -rf "$T"
echo "$NAME lint=[$LINT ] eqy=[$EQ ] blocks=$BT"
