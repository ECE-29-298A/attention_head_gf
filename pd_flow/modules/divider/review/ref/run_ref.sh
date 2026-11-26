#!/bin/bash
# Agent 2 independent reference: SBY k-induction of div_spec.sv against a divider RTL.
# Usage: run_ref.sh <divider.v> <outdir> <LATCH> <CHECK> [mode=prove|cover|bmc] [depth=27] [engine=smtbmc z3] [extra chparam, e.g. "-set REFDIV 1"]
set -u
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:$HOME/.local/bin:/opt/homebrew/bin:$PATH"
DUT=$(cd "$(dirname "$1")" && pwd)/$(basename "$1"); OUT=$2; L=$3; C=$4; MODE=${5:-prove}; DEPTH=${6:-27}; ENG=${7:-smtbmc z3}; XP=${8:-}
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
rm -f "$OUT/divider.v" "$OUT/div_spec.sv" "$OUT/edge_table.vh" "$OUT/edge_n.vh"; cp "$DUT" "$OUT/divider.v"; cp "$HERE/div_spec.sv" "$HERE/edge_table.vh" "$HERE/edge_n.vh" "$OUT/"; chmod u+w "$OUT"/*.v "$OUT"/*.sv
cat > "$OUT/ref.sby" <<SBY
[options]
mode $MODE
depth $DEPTH

[engines]
$ENG

[script]
read_verilog -sv divider.v
read_verilog -formal -sv div_spec.sv
chparam -set LATCH $L -set CHECK $C $XP div_spec
hierarchy -top div_spec
proc
flatten
cd div_spec
connect -set w_state dut.state
connect -set w_step dut.step
connect -set w_q dut.quotient
connect -set w_r dut.remainder_value
connect -set w_neg dut.negative
connect -set w_div dut.divisor
connect -set w_inv dut.invalid_r
cd
prep -top div_spec
check -assert

[files]
divider.v
div_spec.sv
edge_table.vh
edge_n.vh
SBY
cd "$OUT" && /usr/local/bin/python3 ~/.local/bin/sby -f ref.sby > sby.log 2>&1
rc=$?
st=$(grep -o "DONE ([A-Z]*" sby.log | tail -1 | sed 's/DONE (//')
echo "$st rc=$rc $(grep -o 'Elapsed clock time.*' sby.log | tail -1)"
exit $rc
