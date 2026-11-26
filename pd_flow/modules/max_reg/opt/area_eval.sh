#!/bin/bash
# area_eval.sh <cand.v> : copy original_rtl, replace max_reg.v, run synth_area.py (unchanged
# recipe, default ABC, exploration only) for max_reg and tt_um_attention_head_gf.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
C="$1"; NAME=$(basename "$C" .v)
D="$HERE/runs/$NAME"; mkdir -p "$D"
rm -rf "$D/rtl"; cp -R "$HERE/../../../baseline/original_rtl" "$D/rtl"
cp "$C" "$D/rtl/max_reg.v"
/usr/local/bin/python3 "$HERE/../../../scripts/synth_area.py" --rtl "$D/rtl" --out "$D/area.json" \
    max_reg tt_um_attention_head_gf > "$D/area.txt"
echo "$NAME $(awk '{printf "%s=%s ", $1, $2}' "$D/area.txt")"
