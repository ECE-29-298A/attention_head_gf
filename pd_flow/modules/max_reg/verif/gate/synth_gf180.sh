#!/bin/bash
# Map max_reg to GF180 7-track cells with the recipe of pd_flow/scripts/synth_area.py
# (synth -flatten; dfflibmap; abc -liberty, TT 025C 3V30), then write_verilog -noattr.
# Test input for run_all.sh --gate (the golden RTL as a gate-level netlist).
# Usage: synth_gf180.sh <out.v> [rtl.v]
set -eu
export PATH="/opt/homebrew/bin:$PATH"
OUTV=$1
HERE="$(cd "$(dirname "$0")" && pwd)"
RTL="${2:-$HERE/../../../../baseline/original_rtl/max_reg.v}"
LIB=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib
T="$(mktemp -d "${TMPDIR:-/tmp}/mr_synth.XXXXXX")"
cp "$RTL" "$T/max_reg.v"
( cd "$T" && yosys -q -l synth.log -p "read_liberty -lib $LIB; read_verilog -sv max_reg.v; hierarchy -check -top max_reg; synth -flatten -top max_reg; dfflibmap -liberty $LIB; abc -liberty $LIB; opt_clean -purge; check -assert; tee -o stat.txt stat -liberty $LIB; write_verilog -noattr out.v" )
cp "$T/out.v" "$OUTV"
cp "$T/stat.txt" "${OUTV%.v}.stat.txt"
grep "Chip area" "$T/stat.txt"
rm -rf "$T"
