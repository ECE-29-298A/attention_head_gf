#!/bin/bash
# The TT precheck's gf180mcuD KLayout checks (tt/precheck/precheck.py, tt-gds-action@ttgf26c), with the
# PDK version that action installs (open_pdks e8daeda73ca8f5814dbc0b11d1d05802251a3750, fetched
# read-only into /Users/samuelzhang/ttharden/md_pdk_tt by `ciel fetch`; the shared PDK is untouched):
#   "KLayout GF180MCU DRC": gf180mcu.drc variant=gf180mcuD run_mode=deep threads=1 decks=all,-density,-antenna
#   "Antenna check":        gf180mcu.drc variant=gf180mcuD run_mode=deep threads=1 decks=antenna
# usage: [TOP=<topcell>] [DECKS=...] run_tt_precheck_drc.sh <outdir> <gds>...
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
export PATH="$HERE/shim:$PATH"
K=/Applications/klayout.app/Contents/MacOS/klayout
P=/Users/samuelzhang/ttharden/md_pdk_tt/ciel/gf180mcu/versions/e8daeda73ca8f5814dbc0b11d1d05802251a3750/gf180mcuD
DRC=$P/libs.tech/klayout/tech/drc/gf180mcu.drc
OUT="$1"; shift; mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
for g in "$@"; do
    g=$(cd "$(dirname "$g")" && pwd)/$(basename "$g"); b=$(basename "$g" .gds); b=${b%.gds}
    for deck in "${DECKS:-all,-density,-antenna}" antenna; do
        tag=$([ "$deck" = antenna ] && echo antenna || echo drc)
        $K -b -r $DRC -rd input="$g" -rd topcell="${TOP:-TOP}" -rd variant=gf180mcuD -rd run_mode=deep \
            -rd threads=${THREADS:-1} -rd decks="$deck" -rd report="$OUT/$b.$tag.lyrdb" > "$OUT/$b.$tag.log" 2>&1
        echo "$b $tag rc=$? $(python3 "$HERE/lyrdb_summary.py" "$OUT/$b.$tag.lyrdb" 2>&1 | head -1)"
    done
done
