#!/bin/bash
# msynth.sh <file.v> <top> [default|area2]: quick native module synth (exploration only).
LIB=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib
HERE="$(cd "$(dirname "$0")" && pwd)"
T=$(mktemp -d); cp "$1" $T/in.v; cp "$HERE/AREA_2.abc" $T/
if [ "${3:-default}" = area2 ]; then ABC="abc -script $T/AREA_2.abc -liberty $LIB"; else ABC="abc -liberty $LIB"; fi
cat > $T/s.ys <<Y
read_liberty -lib $LIB
read_verilog -sv $T/in.v
chparam -set REGISTERED 0 $2
synth -flatten -top $2
$ABC
opt_clean -purge
tee -o $T/stat.txt stat -liberty $LIB
Y
yosys -q -s $T/s.ys >/dev/null 2>$T/err || { cat $T/err; exit 1; }
echo "$(basename $1 .v) $2 ${3:-default} $(grep -o 'Chip area for.*' $T/stat.txt | awk '{print $NF}')"
rm -rf $T
