#!/bin/bash
# Agent 2: map mac_unit (OUTPUTS=8) to GF180 7-track cells (recipe of pd_flow/scripts/synth_area.py:
# synth -flatten; dfflibmap; abc -liberty, TT 025C 3V30), write_verilog -noattr.
# Usage: gate_synth.sh <out.v> [mac_unit.v] [ripple_add.v]
set -eu
export PATH="/opt/homebrew/bin:$PATH"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUTV=$1; RTL="${2:-$HERE/golden_copy/mac_unit.v}"; RA="${3:-$HERE/golden_copy/ripple_add.v}"
LIB=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib
T="$(mktemp -d "${TMPDIR:-/tmp}/mac_synth.XXXXXX")"
cp "$RTL" "$T/mac_unit.v"; cp "$RA" "$T/ripple_add.v"
( cd "$T" && yosys -q -l synth.log -p "read_liberty -lib $LIB; read_verilog -sv mac_unit.v ripple_add.v; hierarchy -check -top mac_unit; synth -flatten -top mac_unit; dfflibmap -liberty $LIB; abc -liberty $LIB; opt_clean -purge; check -assert; tee -o stat.txt stat -liberty $LIB; write_verilog -noattr out.v" )
cp "$T/out.v" "$OUTV"; cp "$T/stat.txt" "${OUTV%.v}.stat.txt"
grep "Chip area" "$T/stat.txt"; rm -rf "$T"
