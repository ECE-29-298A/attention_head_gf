#!/bin/bash
# area_eval.sh <cand.v> : copy original_rtl, replace ripple_add.v, run synth_area.py
# (unchanged recipe) for ripple_add_22, ripple_add_12, mac_unit, tt_um_attention_head_gf.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
C="$1"; NAME=$(basename "$C" .v)
D="$HERE/runs/$NAME"; mkdir -p "$D"
rm -rf "$D/rtl"; cp -R "$HERE/../../../baseline/original_rtl" "$D/rtl"
cp "$C" "$D/rtl/ripple_add.v"
/usr/local/bin/python3 "$HERE/../../../scripts/synth_area.py" --rtl "$D/rtl" --out "$D/area.json" \
    ripple_add_22 ripple_add_12 mac_unit tt_um_attention_head_gf > "$D/area.txt"
echo "$NAME $(awk '{printf "%s=%s ", $1, $2}' "$D/area.txt")"
