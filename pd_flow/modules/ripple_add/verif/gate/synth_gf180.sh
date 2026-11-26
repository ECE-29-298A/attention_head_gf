#!/bin/bash
# Map the golden ripple_add to GF180 7-track cells with the recipe of
# pd_flow/scripts/synth_area.py (synth -flatten; dfflibmap; abc -liberty, TT 025C 3V30),
# then write_verilog -noattr. Test input for run_all.sh --gate.
# Usage: synth_gf180.sh <N> <out.v> [rtl.v]
set -eu
export PATH="/opt/homebrew/bin:$PATH"
N=$1; OUTV=$2
HERE="$(cd "$(dirname "$0")" && pwd)"
RTL="${3:-$HERE/../../../../baseline/original_rtl/ripple_add.v}"
LIB=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib
T="$(mktemp -d "${TMPDIR:-/tmp}/ra_synth.XXXXXX")"
cp "$RTL" "$T/ripple_add.v"
( cd "$T" && yosys -q -l synth.log -p "read_liberty -lib $LIB; read_verilog -sv ripple_add.v; chparam -set N $N ripple_add; hierarchy -check -top ripple_add; synth -flatten -top ripple_add; dfflibmap -liberty $LIB; abc -liberty $LIB; opt_clean -purge; check -assert; tee -o stat.txt stat -liberty $LIB; write_verilog -noattr out.v" )
cp "$T/out.v" "$OUTV"
cp "$T/stat.txt" "${OUTV%.v}.stat.txt"
grep "Chip area" "$T/stat.txt"
rm -rf "$T"
