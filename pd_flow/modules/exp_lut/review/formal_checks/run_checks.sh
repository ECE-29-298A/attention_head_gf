#!/bin/bash
# Agent 2 formal checks on copies of Agent 1's harness (verif/ is never modified).
#   depth1:   prove_r1 with induction depth 1 (SPEC claims 1-inductiveness)
#   rom:      the .sby with plain `proc` instead of `proc -norom` (is -norom needed, or masking?)
# Runs one SBY at a time (Agent 2 budget). Results in formal_checks/<check>/status.txt.
set -u
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:$HOME/.local/bin:/opt/homebrew/bin:$PATH"
HERE="$(cd "$(dirname "$0")" && pwd)"
V="$HERE/../../verif"
T="$(mktemp -d "${TMPDIR:-/tmp}/el_fc.XXXXXX")"
cp "$V/formal/exp_lut_props.sv" "$V/formal/exp_lut.sby" "$V/logs/ref_table.vh" "$T/"
cp "$HERE/../golden_copy/exp_lut.v" "$T/exp_lut_fv.v"; echo '// RTL mode' > "$T/fv_mode.vh"
run() { # dir task sbyfile
  mkdir -p "$T/$1"; cp "$T"/exp_lut_props.sv "$T"/ref_table.vh "$T"/fv_mode.vh "$T"/exp_lut_fv.v "$T/$1/"; cp "$3" "$T/$1/exp_lut.sby"
  ( cd "$T/$1" && timeout 600 /usr/local/bin/python3 "$HOME/.local/bin/sby" -f exp_lut.sby "$2" > "sby_$2.log" 2>&1 )
  mkdir -p "$HERE/$1"; cp "$T/$1/sby_$2.log" "$HERE/$1/"
  echo "$1 $2 status=$(awk '{print $1}' "$T/$1/exp_lut_$2/status" 2>/dev/null) $(grep -m1 -o 'summary: [^,]*' "$T/$1/sby_$2.log") $(grep -m1 'ERROR' "$T/$1/sby_$2.log" | cut -c1-140)" | tee -a "$HERE/$1/status.txt"
}
rm -f "$HERE/depth1/status.txt" "$HERE/rom/status.txt"
sed 's/^prove: depth 4/prove: depth 1/' "$T/exp_lut.sby" > "$T/d1.sby"
grep -q '^prove: depth 1' "$T/d1.sby" || { echo "depth edit failed"; exit 1; }
for t in prove_r1; do run depth1 $t "$T/d1.sby"; done
sed 's/^proc -norom$/proc/' "$T/exp_lut.sby" > "$T/rom.sby"
grep -q '^proc$' "$T/rom.sby" || { echo "proc edit failed"; exit 1; }
for t in prove_r1 cover_r1; do run rom $t "$T/rom.sby"; done
rm -rf "$T"
