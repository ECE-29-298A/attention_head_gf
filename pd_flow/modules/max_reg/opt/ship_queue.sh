#!/bin/bash
# ship_queue.sh name... : run ll_synth.sh on runs/<name>/rtl, 2 at a time; tag mr_<name>.
# Copies stat.json and the synthesized netlist back to shipped_flow/.
HERE="$(cd "$(dirname "$0")" && pwd)"
LL="$HERE/../../../scripts/ll_synth.sh"
one() {
    local n=$1 t=mr_$1
    "$LL" "$HERE/runs/$n/rtl" "$t" > "$HERE/shipped_flow/$n.txt" 2>&1
    local W=/Users/samuelzhang/ttharden/llsynth/$t
    cp "$W"/runs/synth/*-yosys-synthesis/reports/stat.json "$HERE/shipped_flow/$n.stat.json" 2>/dev/null
    cp "$W"/runs/synth/*-yosys-synthesis/*.nl.v "$HERE/shipped_flow/$n.nl.v" 2>/dev/null
    echo "$(tail -1 "$HERE/shipped_flow/$n.txt")"
}
set -- "$@"
while [ $# -gt 0 ]; do
    one "$1" & p1=$!
    if [ $# -gt 1 ]; then one "$2" & p2=$!; wait $p1 $p2; shift 2; else wait $p1; shift; fi
done
