#!/bin/bash
# Agent 2: install F1 (check_interface flop-bit bound) + F2 (eqy init guard) into a fresh copy of
# git archive HEAD and run golden, gate netlists, c_rename, x05b, m16, m17 and x07 through it.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"; R="$HERE/.."; ROOT="$(cd "$R/../../../.." && pwd)"
S=$1; rm -rf "$S"; mkdir -p "$S"
( cd "$ROOT" && git archive HEAD pd_flow/modules/mac_unit/verif pd_flow/modules/mac_unit/snapshot ) | tar -x -C "$S"
( cd "$S" && git apply --directory=pd_flow/modules/mac_unit "$HERE/F1_F2.patch" ) || { echo PATCH_FAIL; exit 1; }
V="$S/pd_flow/modules/mac_unit/verif"; O="$HERE/runs"; mkdir -p "$O"
"$V/run_all.sh" --jobs 2 --out "$O/golden" --rtl "$S/pd_flow/modules/mac_unit/snapshot/mac_unit.v" > "$O/golden.txt" 2>&1; echo "golden rc=$?"
"$V/run_all.sh" --jobs 2 --rtl "$V/gate/netlists/mac_unit_8_gf180.v" --gate --config 8 --out "$O/gate8" > "$O/gate8.txt" 2>&1; echo "gate8 rc=$?"
"$V/run_all.sh" --jobs 2 --rtl "$V/gate/netlists/mac_unit_2_gf180.v" --gate --config 2 --out "$O/gate2" > "$O/gate2.txt" 2>&1; echo "gate2 rc=$?"
for f in attacks/c_rename attacks/x05b_powerup_flag_O0_consistent mutants/m16_powerup_init_all mutants/m17_powerup_init_L attacks2/x07_initstate_O0 mutants/e01_plus_adder; do b=$(basename $f)
  "$V/run_all.sh" --jobs 2 --rtl "$R/$f.v" --out "$O/$b" > "$O/$b.txt" 2>&1; echo "$b rc=$?"
done
