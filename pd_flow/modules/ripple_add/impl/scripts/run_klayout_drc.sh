#!/bin/bash
# Full GF180 KLayout DRC (PDK deck, unmodified) on a GDS, plus the PDK antenna and density decks.
# Usage: run_klayout_drc.sh GDS TOPCELL OUTDIR [tag]
#   main deck: gf180mcu.drc, variant D switches (metal_top=11K, metal_level=5LM, mim_option=B,
#   as run_drc.py --variant=D), feol/beol/offgrid/conn_drc = true, run_mode=deep.
#   Writes OUTDIR/<tag>_{main,antenna,density}.lyrdb + .log and OUTDIR/<tag>_summary.json.
set -euo pipefail
GDS=$1; TOP=$2; OUT=$3; TAG=${4:-$TOP}
K=/Applications/klayout.app/Contents/MacOS/klayout
PDKV=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee
D=$PDKV/gf180mcuD/libs.tech/klayout/tech/drc
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUT"
COMMON=(-rd "input=$GDS" -rd "topcell=$TOP" -rd metal_top=11K -rd metal_level=5LM -rd mim_option=B
        -rd thr=4 -rd run_mode=deep)
"$K" -b -r "$D/gf180mcu.drc" "${COMMON[@]}" -rd "report=$OUT/${TAG}_main.lyrdb" \
     -rd feol=true -rd beol=true -rd offgrid=true -rd conn_drc=true -rd split_deep=false \
     > "$OUT/${TAG}_main.log" 2>&1
"$K" -b -r "$D/rule_decks/antenna.drc" "${COMMON[@]}" -rd "report=$OUT/${TAG}_antenna.lyrdb" \
     > "$OUT/${TAG}_antenna.log" 2>&1
"$K" -b -r "$D/rule_decks/density.drc" "${COMMON[@]}" -rd "report=$OUT/${TAG}_density.lyrdb" \
     > "$OUT/${TAG}_density.log" 2>&1
python3 "$HERE/lyrdb_summary.py" "$OUT/${TAG}_summary.json" "$GDS" \
     "$OUT/${TAG}_main.lyrdb" "$OUT/${TAG}_antenna.lyrdb" "$OUT/${TAG}_density.lyrdb"
