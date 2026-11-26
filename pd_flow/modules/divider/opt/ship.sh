#!/bin/bash
# ship.sh <cand.v>... : shipped-flow (x0 config) synthesis via the private ll_synth_x0.sh of a full
# copy of baseline/original_rtl with only divider.v replaced. One job at a time (Agent 3 budget).
# Waits while 2 or more Docker containers are up. Tag dv_<name>. stat.json, netlist and console line
# go to shipped_flow/; cone split (cone.py) to shipped_flow/<name>.cone.json.
HERE="$(cd "$(dirname "$0")" && pwd)"
source /Users/samuelzhang/ttsetup/env.sh >/dev/null 2>&1
for C in "$@"; do
    n=$(basename "$C" .v); t=dv_$n
    while [ "$(docker ps -q | wc -l)" -ge 2 ]; do echo "waiting: 2 containers up" >&2; sleep 20; done
    R="$HERE/runs/$n/rtl"; rm -rf "$R"; mkdir -p "$HERE/runs/$n"; cp -R "$HERE/../../../baseline/original_rtl" "$R"; cp "$C" "$R/divider.v"
    "$HERE/ll_synth_x0.sh" "$R" "$t" > "$HERE/shipped_flow/$n.txt" 2>&1
    W=/Users/samuelzhang/ttharden/llsynth/$t
    cp "$W"/runs/synth/*-yosys-synthesis/reports/stat.json "$HERE/shipped_flow/$n.stat.json" 2>/dev/null
    cp "$W"/runs/synth/*-yosys-synthesis/*.nl.v "$HERE/shipped_flow/$n.nl.v" 2>/dev/null
    python3 "$HERE/cone.py" --json "$HERE/shipped_flow/$n.nl.v" > "$HERE/shipped_flow/$n.cone.json" 2>"$HERE/shipped_flow/$n.cone.err"
    echo "$(tail -1 "$HERE/shipped_flow/$n.txt") $(python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); print("div=%.1f (ff %d/%.1f) shared=%.1f rest=%.1f sha=%s" % (r["div_area"], r["div_flops"], r["div_flop_area"], r["shared_area"], r["rest_area"], r["sha"][:8]))' "$HERE/shipped_flow/$n.cone.json" 2>/dev/null)"
done
