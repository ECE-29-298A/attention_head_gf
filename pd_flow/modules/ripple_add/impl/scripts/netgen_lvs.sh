#!/bin/bash
# Netgen LVS exactly as LibreLane's Netgen.LVS step runs it (same setup.tcl, -blackbox), in the
# LibreLane 3.0.14 container, on a given extracted SPICE and Verilog. Used for negative controls.
# Usage: netgen_lvs.sh LAYOUT.spice NETLIST.v OUTDIR TAG
set -euo pipefail
SP=$1; V=$2; OUT=$3; TAG=$4
source /Users/samuelzhang/ttsetup/env.sh
IMG=ghcr.io/librelane/librelane:3.0.14
PDKV=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee
LIB=$PDKV/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/spice/gf180mcu_fd_sc_mcu7t5v0.spice
W=/Users/samuelzhang/ttharden/ra_impl_netgen_$TAG
rm -rf "$W"; mkdir -p "$W"; cp "$SP" "$W/layout.spice"; cp "$V" "$W/netlist.v"
cat > "$W/lvs.tcl" <<TCL
set circuit1 [readnet spice $W/layout.spice]
set circuit2 [readnet verilog /dev/null]
readnet spice $LIB \$circuit2
readnet verilog $W/netlist.v \$circuit2
set setup [glob /nix/store/*-python3-*-env/lib/python3*/site-packages/librelane/scripts/netgen/setup.tcl]
lvs "\$circuit1 ripple_add" "\$circuit2 ripple_add" \$setup $W/$TAG.rpt -blackbox -json
TCL
set +e
docker run --rm -v "$PDKV:$PDKV" -v "$W:$W" -w "$W" $IMG bash -lc "netgen -batch source $W/lvs.tcl" > "$W/$TAG.log" 2>&1; rc=$?
set -e
mkdir -p "$OUT"; cp "$W/$TAG.log" "$W/$TAG.rpt" "$OUT/" 2>/dev/null || true
grep -E "Final result|match|Netlists do not match|Circuits match" "$W/$TAG.rpt" | tail -3
exit $rc
