#!/bin/bash
# Transistor-level parasitic extraction of the final GDS with Magic (LibreLane 3.0.14 container,
# PDK magicrc/tech unmodified). Full cell geometry (GDS), not the abstract views the flow's
# LVS extraction uses. Extracts devices, area/perimeter/fringe capacitance to substrate and
# coupling capacitance between nets (cthresh 0: every capacitor kept). Wire resistance is not
# extracted (see IMPLEMENTATION.md: longest net 34.6 um, a few ohms against kilo-ohm drivers).
# Output: flat ngspice netlist <OUT>/ripple_add_n<N>_pex.spice
# Usage: magic_extract.sh N
set -euo pipefail
N=$1
HERE="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$HERE/n$N/pex"
source /Users/samuelzhang/ttsetup/env.sh
IMG=ghcr.io/librelane/librelane:3.0.14
PDKV=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee
W=/Users/samuelzhang/ttharden/ra_impl_pex_n$N
rm -rf "$W"; mkdir -p "$W"
cp "$HERE/n$N/run/final/gds/ripple_add.gds" "$W/"
cat > "$W/pex.tcl" <<'TCL'
gds readonly true
gds read ripple_add.gds
load ripple_add
select top cell
extract path ./ext
extract do capacitance
extract do coupling
extract do adjust
extract no resistance
extract warn all
extract all
feedback save ext/extract_feedback.txt
ext2spice format ngspice
ext2spice scale off
ext2spice cthresh 0
ext2spice rthresh 0
ext2spice hierarchy off
ext2spice subcircuit top on
ext2spice global off
ext2spice -p ./ext -o ripple_add_pex.spice
puts "PEX_DONE"
quit -noprompt
TCL
mkdir -p "$W/ext"
set +e
docker run --rm -v "$PDKV:$PDKV" -v "$W:$W" -w "$W" -e PDK_ROOT=$PDKV -e PDK=gf180mcuD $IMG bash -lc \
  "magic -dnull -noconsole -rcfile $PDKV/gf180mcuD/libs.tech/magic/gf180mcuD.magicrc pex.tcl" \
  > "$W/magic_pex.log" 2>&1; rc=$?
set -e
mkdir -p "$OUT"
cp "$W/magic_pex.log" "$W/pex.tcl" "$OUT/"; cp "$W/ext/extract_feedback.txt" "$OUT/" 2>/dev/null || true
cp "$W/ripple_add_pex.spice" "$OUT/ripple_add_n${N}_pex.spice" 2>/dev/null || true
grep -E "PEX_DONE|rror" "$W/magic_pex.log" | tail -5
exit $rc
