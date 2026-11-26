#!/bin/bash
# Phase 4 standalone block harden of ripple_add (LibreLane 3.0.14 in Docker).
# Usage: run_block.sh N            (N = 22 or 12). Run only one at a time (Docker memory).
#   Work dir (space-free): /Users/samuelzhang/ttharden/ra_impl_n<N>
#   Inputs: layout_plan/out/{ripple_add_n<N>.v, block_n<N>.cfg, block_n<N>_pins.cfg} and the
#   config made by make_config.py. Results copied to impl/n<N>/run/.
set -euo pipefail
N=$1
HERE="$(cd "$(dirname "$0")/.." && pwd)"            # .../impl
PLAN="$HERE/../layout_plan/out"
W=/Users/samuelzhang/ttharden/ra_impl_n$N
OUT="$HERE/n$N/run"
rm -rf "$W"; mkdir -p "$W"
cp "$PLAN/ripple_add_n$N.v" "$PLAN/block_n$N.cfg" "$PLAN/block_n${N}_pins.cfg" "$W/"
python3 "$HERE/scripts/make_config.py" "$N" "$W/config.json"
python3 "$HERE/scripts/make_pin_template.py" "$N" "$W/pins_template.def"
source /Users/samuelzhang/ttsetup/env.sh
cd "$W"; mkdir -p runs/impl
t0=$(date +%s)
set +e
python -m librelane --docker-no-tty --dockerized --pdk-root "$PDK_ROOT" --pdk gf180mcuD \
  --run-tag impl --force-run-dir runs/impl config.json > "$W/librelane.log" 2>&1; rc=$?
set -e
echo "librelane rc=$rc seconds=$(( $(date +%s) - t0 ))" | tee "$W/status.txt"
R=$W/runs/impl
rm -rf "$OUT"; mkdir -p "$OUT"
cp "$W/config.json" "$W/pins_template.def" "$W/librelane.log" "$W/status.txt" "$OUT/"
[ -d "$R" ] || exit $rc
cp "$R/resolved.json" "$R/flow.log" "$R/warning.log" "$R/error.log" "$OUT/" 2>/dev/null || true
if [ -d "$R/final" ]; then
  rsync -a --exclude 'render' "$R/final/" "$OUT/final/"
fi
# step logs and reports (no ODB/large intermediate views)
for s in "$R"/[0-9]*-*; do
  b=$(basename "$s"); mkdir -p "$OUT/steps/$b"
  find "$s" -maxdepth 2 -type f \( -name '*.log' -o -name '*.rpt' -o -name '*.json' -o -name '*.txt' \
     -o -name '*.lyrdb' -o -name '*.xml' -o -name '*.drc' -o -name '*.out' \) -size -5M \
     -exec cp {} "$OUT/steps/$b/" \; 2>/dev/null || true
  cp "$s"/*.def "$OUT/steps/$b/" 2>/dev/null || true
  if [ -d "$s/reports" ]; then cp -r "$s/reports" "$OUT/steps/$b/" 2>/dev/null || true; fi
done
find "$OUT/steps" -name '*.def' -exec gzip -9f {} + 2>/dev/null || true
find "$OUT" -type d -empty -delete
exit $rc
