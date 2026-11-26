#!/bin/bash
# Independent transistor-level LVS with the PDK KLayout deck (gf180mcu.lvs, unmodified), the
# switches run_lvs.py would pass for --variant=D --run_mode=deep --lvs_sub=VSUB (run_lvs.py itself
# needs the klayout.db Python module, which the host lacks). The deck's log formatter calls the
# Linux `pmap`; scripts/shim/pmap supplies it on macOS (memory figure only, no effect on LVS).
# Usage: run_klayout_lvs.sh GDS SCHEMATIC.spice OUTDIR TAG [TOPCELL]
set -euo pipefail
GDS=$1; SCH=$2; OUT=$3; TAG=$4; TOP=${5:-ripple_add}
HERE="$(cd "$(dirname "$0")" && pwd)"
export PATH="$HERE/shim:$PATH"
K=/Applications/klayout.app/Contents/MacOS/klayout
PDKV=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee
L=$PDKV/gf180mcuD/libs.tech/klayout/tech/lvs
mkdir -p "$OUT"
set +e
"$K" -b -r "$L/gf180mcu.lvs" -rd "input=$GDS" -rd "schematic=$SCH" -rd "topcell=$TOP" \
  -rd "report=$OUT/${TAG}.lvsdb" -rd "target_netlist=$OUT/${TAG}_extracted.cir" \
  -rd thr=4 -rd "run_mode=${RUN_MODE:-flat}" -rd metal_top=11K -rd mim_option=B -rd metal_level=5LM \
  -rd poly_res=1k -rd mim_cap=2 -rd "lvs_sub=${LVS_SUB:-VSUB}" -rd verbose=false -rd spice_net_names=true \
  -rd spice_comments=false -rd scale=false -rd schematic_simplify=false -rd net_only=false \
  -rd top_lvl_pins=false -rd combine=false -rd purge=false -rd purge_nets=false \
  > "$OUT/${TAG}.log" 2>&1; rc=$?
set -e
echo "klayout rc=$rc" >> "$OUT/${TAG}.log"
grep -iE "congratulations|error|don.t match|netlists match" "$OUT/${TAG}.log" | tail -5
exit $rc
