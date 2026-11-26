#!/bin/bash
# Agent 2: rerun Agent 1's contract from a clean copy (verif/ sources only, no logs/evidence/results;
# snapshot/; python/src) in the scratchpad, golden RTL and both golden gate netlists. --jobs 2.
# Usage: rerun_clean.sh <scratch dir> [rtl|gate|all]   (the copy is (re)made only for rtl/all)
set -u
SRC="$(cd "$(dirname "$0")/../../../.." && pwd)"     # project root
S=$1; WHAT=${2:-all}
if [ "$WHAT" != gate ]; then
rm -rf "$S"; mkdir -p "$S/pd_flow/modules/divider" "$S/python"
rsync -a --exclude logs --exclude formal/runs --exclude evidence --exclude gate/evidence \
      --exclude results.json --exclude run_all.console.log "$SRC/pd_flow/modules/divider/verif/" "$S/pd_flow/modules/divider/verif/"
cp -R "$SRC/pd_flow/modules/divider/snapshot" "$S/pd_flow/modules/divider/"
cp -R "$SRC/python/src" "$S/python/"
( cd "$S/pd_flow/modules/divider/verif" && find . -type f | sort | xargs shasum -a 256 ) > "$(dirname "$0")/rerun/frozen_copy_hashes.txt" 2>/dev/null || true
fi
R="$(cd "$(dirname "$0")" && pwd)/rerun"; mkdir -p "$R"
V="$S/pd_flow/modules/divider/verif"
if [ "$WHAT" != gate ]; then
"$V/run_all.sh" --jobs 2 > "$R/clean_rtl.console.txt" 2>&1; echo "rtl rc=$?"
mkdir -p "$R/clean_rtl"; cp "$V/results.json" "$R/clean_rtl/"
fi
[ "$WHAT" = rtl ] && exit 0
for c in 00 11; do
  "$V/run_all.sh" --rtl "$V/gate/netlists/divider_${c}_gf180.v" --gate --config $c --out "$R/clean_gate_$c" --jobs 2 > "$R/clean_gate_$c.console.txt" 2>&1
  echo "gate $c rc=$?"
done
