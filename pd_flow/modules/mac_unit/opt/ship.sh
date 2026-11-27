#!/bin/bash
# ship.sh <cand.v>... : shipped-flow (x0 config) synthesis via the private ll_synth_x0.sh (copy of the
# divider Agent 3 script) of a full copy of baseline/original_rtl with only mac_unit.v replaced.
# CTX=c06: base is opt/base_c06 (original_rtl + accepted divider c06), tag mc6_<name>, files <name>@c06.*.
# One job at a time (Agent 3 budget); waits while 2 or more Docker containers are up. Tag mc_<name>.
# stat.json, netlist, console line -> shipped_flow/; in-context cone split (cone.py) -> <name>.cone.json.
HERE="$(cd "$(dirname "$0")" && pwd)"
source /Users/samuelzhang/ttsetup/env.sh >/dev/null 2>&1
for C in "$@"; do
    b=$(basename "$C" .v)
    if [ "${CTX:-}" = c06 ]; then n="$b@c06"; t="mc6_$b"; SRC="$HERE/base_c06"; else n=$b; t=mc_$b; SRC="$HERE/../../../baseline/original_rtl"; fi
    while [ "$(docker ps -q | wc -l)" -ge 2 ]; do echo "waiting: 2 containers up" >&2; sleep 20; done
    R="$HERE/runs/$n/rtl"; rm -rf "$R"; mkdir -p "$HERE/runs/$n"; cp -R "$SRC" "$R"; cp "$C" "$R/mac_unit.v"
    "$HERE/ll_synth_x0.sh" "$R" "$t" > "$HERE/shipped_flow/$n.txt" 2>&1
    W=/Users/samuelzhang/ttharden/llsynth/$t
    cp "$W"/runs/synth/*-yosys-synthesis/reports/stat.json "$HERE/shipped_flow/$n.stat.json" 2>/dev/null
    cp "$W"/runs/synth/*-yosys-synthesis/*.nl.v "$HERE/shipped_flow/$n.nl.v" 2>/dev/null
    python3 "$HERE/cone.py" --json "$HERE/shipped_flow/$n.nl.v" > "$HERE/shipped_flow/$n.cone.json" 2>"$HERE/shipped_flow/$n.cone.err"
    echo "$(tail -1 "$HERE/shipped_flow/$n.txt") $(python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); print("mac=%.1f (ff %d, logic %.1f) exp=%.1f shared=%.1f rest=%.1f sha=%s" % (r["mac_area"], r["mac_flops"], r["mac_logic_area"], r["exp_area"], r["shared_area"], r["rest_area"], r["sha"][:8]))' "$HERE/shipped_flow/$n.cone.json" 2>/dev/null)"
done
