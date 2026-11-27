#!/bin/bash
# Map attention_controller (with its frozen submodules) to GF180 7-track cells with the recipe of
# the mac_unit / divider contracts (synth -flatten -nofsm; dfflibmap; abc -liberty, TT 025C 3V30; -nofsm keeps the state encoding and names, as LibreLane does by default... see SPEC 10), then
# write_verilog -noattr. OUTPUTS is set by chparam, so the module keeps the name
# attention_controller and has no parameter left. Test input for run_all.sh --gate --config P
# (the golden RTL as a gate-level netlist; NOT the shipped LibreLane netlist).
# Usage: synth_gf180.sh <out.v> <OUTPUTS 2|4|8> [rtl_dir (default ../snapshot)]
set -eu
export PATH="/opt/homebrew/bin:$PATH"
OUTV=$1
P=$2
case $P in 2|4|8) ;; *) echo "OUTPUTS must be 2, 4 or 8" >&2; exit 2 ;; esac
HERE="$(cd "$(dirname "$0")" && pwd)"
D="${3:-$HERE/../../snapshot}"
LIB=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib
T="$(mktemp -d "${TMPDIR:-/tmp}/ctrl_synth.XXXXXX")"
for f in attention_controller.sv mac_unit.v ripple_add.v max_reg.v exp_lut.v divider.v; do cat "$D/$f"; done > "$T/rtl.sv"
( cd "$T" && yosys -q -l synth.log -p "read_liberty -lib $LIB; read_verilog -sv rtl.sv; chparam -set OUTPUTS $P attention_controller; hierarchy -check -top attention_controller; synth -flatten -nofsm -top attention_controller; dfflibmap -liberty $LIB; abc -liberty $LIB; opt_clean -purge; check -assert; tee -o stat.txt stat -liberty $LIB; write_verilog -noattr out.v" )
cp "$T/out.v" "$OUTV"
cp "$T/stat.txt" "${OUTV%.v}.stat.txt"
grep "Chip area" "$T/stat.txt"
rm -rf "$T"
