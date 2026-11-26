#!/bin/bash
# Agent 2: map exp_lut to GF180 7-track cells, same recipe as modules/max_reg/verif/gate/synth_gf180.sh
# (synth -flatten; dfflibmap; abc -liberty, TT 025C 3V30; write_verilog -noattr), with the
# REGISTERED parameter fixed by chparam so the netlist top keeps the name exp_lut.
# Usage: gate_synth.sh <out.v> <rtl.v> <REGISTERED>
set -eu
export PATH="/opt/homebrew/bin:$PATH"
OUTV=$1; RTL=$2; R=$3
LIB=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib
T="$(mktemp -d "${TMPDIR:-/tmp}/el_synth.XXXXXX")"
cp "$RTL" "$T/exp_lut.v"
( cd "$T" && yosys -q -l synth.log -p "read_liberty -lib $LIB; read_verilog -sv exp_lut.v; chparam -set REGISTERED $R exp_lut; hierarchy -check -top exp_lut; synth -flatten -top exp_lut; dfflibmap -liberty $LIB; abc -liberty $LIB; opt_clean -purge; check -assert; tee -o stat.txt stat -liberty $LIB; write_verilog -noattr out.v" )
cp "$T/out.v" "$OUTV"
cp "$T/stat.txt" "${OUTV%.v}.stat.txt"
echo "$(basename "$OUTV") R=$R $(grep 'Chip area' "$T/stat.txt")"
rm -rf "$T"
