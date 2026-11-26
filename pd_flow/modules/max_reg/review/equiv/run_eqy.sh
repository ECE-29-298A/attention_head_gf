#!/bin/bash
# Usage: run_eqy.sh <mutant.v> <name>   (runs in a space-free temp dir, copies results back)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
M="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"; N=$2
T="$(mktemp -d "${TMPDIR:-/tmp}/mr_eqy.XXXXXX")"
cp "$HERE/../golden_copy/max_reg.v" "$T/gold.v"; cp "$M" "$T/gate.v"; cp "$HERE/template.eqy" "$T/eq.eqy"
( cd "$T" && timeout 600 /usr/local/bin/python3 "$HOME/.local/bin/eqy" -f eq.eqy > eqy.log 2>&1 ); rc=$?
mkdir -p "$HERE/$N"; cp "$T/eqy.log" "$HERE/$N/"; cp "$T/eq/status" "$HERE/$N/" 2>/dev/null
cp -R "$T/eq/partitions" "$HERE/$N/" 2>/dev/null
echo "$N rc=$rc result=$(grep -o "DONE ([A-Z]*" "$T/eqy.log" | tail -1) $(grep -c 'Successfully proved' "$T/eqy.log") partitions proved"
rm -rf "$T"
