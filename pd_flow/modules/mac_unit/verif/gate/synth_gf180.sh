#!/bin/bash
# Map mac_unit to GF180 7-track cells with the recipe of pd_flow/scripts/synth_area.py
# (synth -flatten; dfflibmap; abc -liberty, TT 025C 3V30), then write_verilog -noattr.
# Same recipe as modules/divider/verif/gate/synth_gf180.sh, with OUTPUTS set by chparam (so
# the module keeps the name mac_unit and has no parameter left). No splitnets: the ports stay
# vectors (S[21:0], O0[19:0], ...), as the contract's harnesses instantiate them.
# Test input for run_all.sh --gate --config P (the golden RTL as a gate-level netlist).
# Usage: synth_gf180.sh <out.v> <OUTPUTS 2|4|8> [mac_unit.v [ripple_add.v]]
set -eu
export PATH="/opt/homebrew/bin:$PATH"
OUTV=$1
P=$2
case $P in 2|4|8) ;; *) echo "OUTPUTS must be 2, 4 or 8" >&2; exit 2 ;; esac
HERE="$(cd "$(dirname "$0")" && pwd)"
RTL="${3:-$HERE/../../snapshot/mac_unit.v}"
RA="${4:-$HERE/../../snapshot/ripple_add.v}"
LIB=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib
T="$(mktemp -d "${TMPDIR:-/tmp}/mac_synth.XXXXXX")"
cp "$RTL" "$T/mac_unit.v"
cp "$RA" "$T/ripple_add.v"
( cd "$T" && yosys -q -l synth.log -p "read_liberty -lib $LIB; read_verilog -sv mac_unit.v ripple_add.v; chparam -set OUTPUTS $P mac_unit; hierarchy -check -top mac_unit; synth -flatten -top mac_unit; dfflibmap -liberty $LIB; abc -liberty $LIB; opt_clean -purge; check -assert; tee -o stat.txt stat -liberty $LIB; write_verilog -noattr out.v" )
cp "$T/out.v" "$OUTV"
cp "$T/stat.txt" "${OUTV%.v}.stat.txt"
grep "Chip area" "$T/stat.txt"
rm -rf "$T"
