#!/bin/bash
# Map divider to GF180 7-track cells with the recipe of pd_flow/scripts/synth_area.py
# (synth -flatten; dfflibmap; abc -liberty, TT 025C 3V30), then write_verilog -noattr.
# Same recipe as modules/exp_lut/verif/gate/synth_gf180.sh, with the two parameters set by
# chparam (so the module keeps the name divider and has no parameter left).
# Test input for run_all.sh --gate --config CC (the golden RTL as a gate-level netlist).
# Usage: synth_gf180.sh <out.v> <CONFIG 00|11> [rtl.v]
#   CONFIG: first digit LATCH_DENOMINATOR, second CHECK_INVALID (00 = shipped, 11 = defaults)
set -eu
export PATH="/opt/homebrew/bin:$PATH"
OUTV=$1
CFG=$2
case $CFG in 00|11) ;; *) echo "CONFIG must be 00 or 11" >&2; exit 2 ;; esac
LDV=${CFG:0:1}; CIV=${CFG:1:1}
HERE="$(cd "$(dirname "$0")" && pwd)"  # Agent 2 copy of verif/gate/synth_gf180.sh (RTL argument required)
RTL="${3:-$HERE/../../snapshot/divider.v}"
LIB=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib
T="$(mktemp -d "${TMPDIR:-/tmp}/div_synth.XXXXXX")"
cp "$RTL" "$T/divider.v"
( cd "$T" && yosys -q -l synth.log -p "read_liberty -lib $LIB; read_verilog -sv divider.v; chparam -set LATCH_DENOMINATOR $LDV divider; chparam -set CHECK_INVALID $CIV divider; hierarchy -check -top divider; synth -flatten -top divider; dfflibmap -liberty $LIB; abc -liberty $LIB; opt_clean -purge; check -assert; tee -o stat.txt stat -liberty $LIB; write_verilog -noattr out.v" )
cp "$T/out.v" "$OUTV"
cp "$T/stat.txt" "${OUTV%.v}.stat.txt"
grep "Chip area" "$T/stat.txt"
rm -rf "$T"
