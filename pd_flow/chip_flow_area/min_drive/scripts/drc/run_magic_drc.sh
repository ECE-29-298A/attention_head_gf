#!/bin/bash
# Magic DRC (LibreLane 3.0.14 image's magic, PDK gf180mcuD magicrc/tech) on test GDS files.
# usage: [TOP=<topcell>] run_magic_drc.sh <outdir> <gds>...    (all paths absolute, space-free)
set -uo pipefail
PDKV=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$1"; shift; mkdir -p "$OUT"
TCL=$OUT/magic_drc.tcl; cp "$HERE/magic_drc.tcl" "$TCL"
source /Users/samuelzhang/ttsetup/env.sh
D=$(dirname "$OUT")
cmds=""
for g in "$@"; do
    b=$(basename "$g" .gds)
    cmds+="GDS=$g TOPCELL=${TOP:-TOP} RPT=$OUT/$b.magic.rpt PDK_ROOT=$PDKV magic -dnull -noconsole -rcfile $PDKV/gf180mcuD/libs.tech/magic/gf180mcuD.magicrc $TCL > $OUT/$b.magic.log 2>&1; echo $b \$(grep -h MAGIC_DRC_COUNT $OUT/$b.magic.log); "
done
while [ "$(docker ps --format "{{.Image}}" | grep -c librelane)" -ge 2 ]; do sleep 20; done  # machine-wide limit
docker run --rm -v "$PDKV:$PDKV" -v "$D:$D" -w "$D" ghcr.io/librelane/librelane:3.0.14 bash -lc "$cmds"
for g in "$@"; do b=$(basename "$g" .gds); grep "^==" "$OUT/$b.magic.rpt" | sort | uniq -c | sed "s/^/  $b: /"; done
