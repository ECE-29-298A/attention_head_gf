#!/bin/bash
# Agent 2: EQY equivalence of the golden exp_lut against a candidate (RTL or GF180 netlist).
# Usage: run_eqy.sh <candidate.v> <name> <REGISTERED> [rtl|gate]
#   rtl : candidate read as RTL with chparam REGISTERED
#   gate: candidate is a mapped netlist; its Yosys view (netlist + PDK comb. models + liberty flop
#         models) is built with modules/max_reg/verif/gate/extract_cells.py, then flattened with
#         opt_clean so non-inverting clock buffers collapse.
# memory_map turns the case-statement ROM (proc_rom) into logic; EQY sat refuses memories.
# Strategy sat depth 1: REGISTERED=0 is combinational (a complete proof); REGISTERED=1 has the
# 9 state bits matched by name (W_r/done_r in the RTL, the flop Q nets W/done in a netlist), so
# depth 1 is an unbounded proof of the next-state and output functions.
set -u
export PATH="/opt/homebrew/bin:$PATH"
HERE="$(cd "$(dirname "$0")" && pwd)"
M="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"; N=$2; R=$3; KIND=${4:-rtl}
PDKSC=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0
XC="$HERE/../../../max_reg/verif/gate/extract_cells.py"
T="$(mktemp -d "${TMPDIR:-/tmp}/el_eqy.XXXXXX")"
cp "$HERE/../golden_copy/exp_lut.v" "$T/gold.v"
if [ "$KIND" = gate ]; then
  /usr/local/bin/python3 "$XC" "$M" "$PDKSC/verilog" "$PDKSC/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib" "$T/sim.v" "$T/gate.v" > "$T/xc.log" 2>&1 \
    || { echo "$N extract_cells FAIL"; cat "$T/xc.log"; rm -rf "$T"; exit 2; }
  GATE="read_verilog gate.v
hierarchy -top exp_lut
proc; flatten; opt_clean
prep -top exp_lut
memory_map; opt_clean"
else
  cp "$M" "$T/gate.v"
  GATE="read_verilog -sv gate.v
chparam -set REGISTERED $R exp_lut
prep -top exp_lut
memory_map; opt_clean"
fi
cat > "$T/eq.eqy" <<EOF
[gold]
read_verilog -sv gold.v
chparam -set REGISTERED $R exp_lut
prep -top exp_lut
memory_map; opt_clean

[gate]
$GATE

[strategy sat]
use sat
depth 1
EOF
( cd "$T" && timeout 900 /usr/local/bin/python3 "$HOME/.local/bin/eqy" -f eq.eqy > eqy.log 2>&1 ); rc=$?
mkdir -p "$HERE/$N"; cp "$T/eq.eqy" "$T/eqy.log" "$HERE/$N/"; cp "$T/eq/status" "$HERE/$N/" 2>/dev/null
res=$(grep -o "DONE ([A-Z]*" "$T/eqy.log" | tail -1 | sed 's/DONE (//')
echo "$N rc=$rc result=${res:-none} $(grep -c 'Successfully proved' "$T/eqy.log") partitions proved"
echo "{\"name\": \"$N\", \"registered\": $R, \"kind\": \"$KIND\", \"rc\": $rc, \"result\": \"${res:-none}\"}" > "$HERE/$N/result.json"
rm -rf "$T"
