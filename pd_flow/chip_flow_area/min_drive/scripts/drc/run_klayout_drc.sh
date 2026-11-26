#!/bin/bash
# Full GF180 KLayout DRC deck (PDK gf180mcu.drc, host KLayout) on test GDS files.
# usage: [TOP=<topcell>] run_klayout_drc.sh <outdir> <conn: 0|1> <gds>...   (topcell default TOP)
# Flags are the AGENT_CONTEXT command (feol, beol, offgrid, deep mode); conn=1 adds conn_drc=true
# (the connectivity-aware rule variants, as the TT precheck full deck runs them).
set -uo pipefail
K=/Applications/klayout.app/Contents/MacOS/klayout
PDKV=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee
DRC=$PDKV/gf180mcuD/libs.tech/klayout/tech/drc/gf180mcu.drc
OUT="$1"; CONN="$2"; shift 2
mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
for g in "$@"; do
    g=$(cd "$(dirname "$g")" && pwd)/$(basename "$g")
    b=$(basename "$g" .gds)
    top="${TOP:-TOP}"
    extra=""; [ "$CONN" = 1 ] && extra="-rd conn_drc=true"
    /usr/bin/time -p $K -b -r $DRC -rd input="$g" -rd topcell="$top" -rd report="$OUT/$b.lyrdb" \
        -rd feol=true -rd beol=true -rd offgrid=true -rd run_mode=deep -rd thr=2 $extra > "$OUT/$b.log" 2>&1
    echo "$b rc=$? $(python3 "$(dirname "$0")/lyrdb_summary.py" "$OUT/$b.lyrdb" | head -1)"
done
