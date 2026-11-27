#!/bin/bash
# Agent 2 independent reference: SBY proof of mac_spec.sv against a mac_unit RTL (any start state).
# GATE=1: DUT is a GF180 netlist; cell functions come from read_liberty (no ripple_add).
# Usage: run_ref.sh <mac_unit.v> <outdir> [mode=prove|cover] [depth=4] [ripple_add.v]
set -u
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"
abspath() { echo "$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"; }
HERE="$(cd "$(dirname "$0")" && pwd)"
DUT=$(abspath "$1"); OUT=$2; MODE=${3:-prove}; DEPTH=${4:-4}; RA=$(abspath "${5:-$HERE/../golden_copy/ripple_add.v}")
mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
rm -rf "$OUT"/ref "$OUT"/*.v "$OUT"/*.sv; cp "$DUT" "$OUT/mac_unit.v"; cp "$RA" "$OUT/ripple_add.v"; cp "$HERE/mac_spec.sv" "$OUT/"; chmod u+w "$OUT"/*.v "$OUT"/*.sv
DEF=""; [ "$MODE" = cover ] && DEF="-DREF_COVERS"
LIB=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib
if [ "${GATE:-0}" = 1 ]; then READRA="read_liberty -ignore_miss_func $LIB"; DEF="$DEF -DGATE"; else READRA="read_verilog -sv ripple_add.v"; fi
cat > "$OUT/ref.sby" <<SBY
[options]
mode $MODE
depth $DEPTH

[engines]
smtbmc z3

[script]
read_verilog -sv mac_unit.v
$READRA
read_verilog -formal -sv $DEF mac_spec.sv
hierarchy -top mac_spec
proc
# guards (whole design; the spec itself has none): no init values, no formal cells in the DUT,
# no latches/async flops
select -assert-none a:init
select -assert-none t:\$assume t:\$assert t:\$cover t:\$check t:\$live t:\$fair %u %u %u %u %u mac_spec/* %d
select -assert-none t:\$dlatch t:\$adff t:\$adffe t:\$dffsr t:\$aldff t:\$sr
flatten
connect -set w_ring dut.ring
prep -top mac_spec
check -assert

[files]
mac_unit.v
ripple_add.v
mac_spec.sv
SBY
cd "$OUT" && /usr/local/bin/python3 ~/.local/bin/sby -f ref.sby > sby.log 2>&1
rc=$?
st=$(grep -o "DONE ([A-Z]*" sby.log | tail -1 | sed 's/DONE (//')
echo "$st rc=$rc $(grep -o 'Elapsed clock time.*' sby.log | tail -1)"
exit $rc
