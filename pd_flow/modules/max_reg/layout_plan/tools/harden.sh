#!/bin/bash
# Full shipped-flow harden of a candidate chip RTL in its own space-free mirror (adapted from ripple_add).
# Usage: harden.sh <tag> <rtl_dir> [overlay.json [extra_file_for_src ...]]
#   Mirror: /Users/samuelzhang/ttharden/mr3_<tag> (copy of ttharden/attention_head_gf without runs/),
#   the 7 shipped files replaced from <rtl_dir>; optional overlay.json keys are merged into
#   the mirror's src/config.json (never the project's). Runs tt/tt_tool.py --harden.
#   Evidence copied to layout_plan/chip_runs/<tag>/harden/. Run only one at a time.
set -euo pipefail
TAG=$1; RTL="$(cd "$2" && pwd)"; OVL="${3:-}"
[ -n "$OVL" ] && OVL="$(cd "$(dirname "$OVL")" && pwd)/$(basename "$OVL")"
EXTRA=()
if [ $# -gt 3 ]; then for x in "${@:4}"; do EXTRA+=("$(cd "$(dirname "$x")" && pwd)/$(basename "$x")"); done; fi
HERE="$(cd "$(dirname "$0")/.." && pwd)"
SRC=/Users/samuelzhang/ttharden/attention_head_gf
M=/Users/samuelzhang/ttharden/mr3_$TAG
OUT="$HERE/chip_runs/$TAG/harden"
rm -rf "$M"; mkdir -p "$M"
rsync -a --exclude runs "$SRC/" "$M/"
for f in project.v attention_controller.sv mac_unit.v ripple_add.v max_reg.v exp_lut.v divider.v; do
  cp "$RTL/$f" "$M/src/$f"
done
if [ -n "$OVL" ]; then
  python3 - "$M/src/config.json" "$OVL" <<'PY'
import json, sys
c = json.load(open(sys.argv[1])); o = json.load(open(sys.argv[2]))
c.update(o); json.dump(c, open(sys.argv[1], "w"), indent=2)
print("overlay keys:", sorted(o))
PY
  cp "$OVL" "$M/overlay.json"
fi
for x in ${EXTRA[@]+"${EXTRA[@]}"}; do cp "$x" "$M/src/"; done
source /Users/samuelzhang/ttsetup/env.sh
cd "$M"
t0=$(date +%s)
set +e
python tt/tt_tool.py --pdk gf180mcuD --harden > "$M/tt_tool_harden.log" 2>&1; rc=$?
set -e
echo "harden rc=$rc seconds=$(( $(date +%s) - t0 ))" | tee "$M/harden_status.txt"
rm -rf "$OUT"; mkdir -p "$OUT"
cp "$M/tt_tool_harden.log" "$M/harden_status.txt" "$OUT/"
[ -n "$OVL" ] && cp "$OVL" "$OUT/overlay.json"
for x in ${EXTRA[@]+"${EXTRA[@]}"}; do cp "$x" "$OUT/"; done
R=$M/runs/wokwi
[ -d "$R" ] || exit $rc
cp "$R/resolved.json" "$R/flow.log" "$OUT/" 2>/dev/null || true
cp "$R/warning.log" "$R/error.log" "$OUT/" 2>/dev/null || true
if [ -d "$R/final" ]; then
  cp "$R/final/metrics.json" "$R/final/metrics.csv" "$OUT/" 2>/dev/null || true
  mkdir -p "$OUT/def" "$OUT/nl" "$OUT/pnl"
  cp "$R"/final/def/*.def "$OUT/def/"; cp "$R"/final/nl/*.v "$OUT/nl/"; cp "$R"/final/pnl/*.v "$OUT/pnl/"
fi
# per-step snapshots needed to check placement semantics (after manual macro placement, GPL, DPL, CTS)
for s in "$R"/*-odb-manualmacroplacement "$R"/*-openroad-globalplacement "$R"/*-openroad-detailedplacement "$R"/*-openroad-cts; do
  [ -d "$s" ] || continue; b=$(basename "$s"); mkdir -p "$OUT/steps/$b"
  cp "$s"/*.def "$s"/*.log "$OUT/steps/$b/" 2>/dev/null || true
done
for c in "$R"/*-openroad-stapostpnr; do
  [ -d "$c" ] || continue
  mkdir -p "$OUT/sta_postpnr"; cp "$c"/summary.rpt "$OUT/sta_postpnr/" 2>/dev/null || true
  for d in "$c"/*/; do d=${d%/}; n=$(basename "$d"); mkdir -p "$OUT/sta_postpnr/$n"; cp "$d"/max.rpt "$d"/min.rpt "$d"/power.rpt "$d"/checks.rpt "$d"/skew*.rpt "$OUT/sta_postpnr/$n/" 2>/dev/null || true; done
done
cp "$R"/*-yosys-synthesis/reports/stat.json "$OUT/synth_stat.json" 2>/dev/null || true
find "$OUT/sta_postpnr" -name "*.rpt" -exec gzip -9 {} + 2>/dev/null || true
find "$OUT" -type d -empty -delete
( cd "$OUT" && find . -type f ! -name SHA256SUMS -exec shasum -a 256 {} + > SHA256SUMS )
exit $rc
