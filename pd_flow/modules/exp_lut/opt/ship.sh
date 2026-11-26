#!/bin/bash
# ship.sh <cand.v>... : shipped-flow synthesis (scripts/ll_synth.sh) of a full copy of
# baseline/original_rtl with only exp_lut.v replaced. One job at a time (Agent 3 budget). Before each
# run, waits while any other Docker container is running (a LibreLane harden blocks ll_synth).
# Tag el_<name>. stat.json, netlist and the console line go to shipped_flow/ (netlists: git-ignored
# bulk, see .gitignore); the cone split of the netlist is appended to shipped_flow/<name>.cone.json.
HERE="$(cd "$(dirname "$0")" && pwd)"
LL="$HERE/../../../scripts/ll_synth.sh"
source /Users/samuelzhang/ttsetup/env.sh >/dev/null 2>&1
for C in "$@"; do
    n=$(basename "$C" .v); t=el_$n
    while [ -n "$(docker ps -q)" ]; do echo "waiting: docker busy ($(docker ps --format '{{.Image}} {{.Names}}' | head -1))" >&2; sleep 30; done
    R="$HERE/runs/$n/rtl"; rm -rf "$R"; mkdir -p "$HERE/runs/$n"; cp -R "$HERE/../../../baseline/original_rtl" "$R"; cp "$C" "$R/exp_lut.v"
    "$LL" "$R" "$t" > "$HERE/shipped_flow/$n.txt" 2>&1
    W=/Users/samuelzhang/ttharden/llsynth/$t
    cp "$W"/runs/synth/*-yosys-synthesis/reports/stat.json "$HERE/shipped_flow/$n.stat.json" 2>/dev/null
    cp "$W"/runs/synth/*-yosys-synthesis/*.nl.v "$HERE/shipped_flow/$n.nl.v" 2>/dev/null
    python3 "$HERE/cone.py" --json "$HERE/shipped_flow/$n.nl.v" > "$HERE/shipped_flow/$n.cone.json" 2>/dev/null
    echo "$(tail -1 "$HERE/shipped_flow/$n.txt") $(python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); print("exp=%.1f shared=%.1f rest=%.1f" % (r["exp_area"], r["shared_dOnly_area"], r["rest_area"]))' "$HERE/shipped_flow/$n.cone.json" 2>/dev/null)"
done
