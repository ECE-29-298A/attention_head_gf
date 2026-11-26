#!/bin/bash
# area_eval.sh <cand.v>... : for each, copy baseline/original_rtl to runs/<name>/rtl with exp_lut.v
# replaced, and run synth_area.py (default ABC, exploration only) for exp_lut (REGISTERED=0).
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
for C in "$@"; do
    NAME=$(basename "$C" .v); D="$HERE/runs/$NAME"; mkdir -p "$D"
    rm -rf "$D/rtl"; cp -R "$HERE/../../../baseline/original_rtl" "$D/rtl"; cp "$C" "$D/rtl/exp_lut.v"
    /usr/local/bin/python3 "$HERE/../../../scripts/synth_area.py" --rtl "$D/rtl" --out "$D/area.json" exp_lut > "$D/area.txt"
    echo "$NAME $(awk '{printf "%s=%s cells=%s", $1, $2, $5}' "$D/area.txt")"
done
