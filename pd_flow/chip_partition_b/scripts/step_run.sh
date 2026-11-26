#!/bin/bash
# Run one LibreLane 3.0.14 step standalone (Docker): step_run.sh <step_id> <config.json> <state_in.json> <outdir>
set -euo pipefail
ID="$1"; CFG="$2"; ST="$3"; OUT="$4"
PDKV=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee
source /Users/samuelzhang/ttsetup/env.sh
mkdir -p "$OUT"
docker run --rm -v "$PDKV:$PDKV" -v /Users/samuelzhang/ttharden:/Users/samuelzhang/ttharden -w "$OUT" \
  ghcr.io/librelane/librelane:3.0.14 bash -lc "python3 -m librelane.steps run --id $ID -c $CFG -i $ST -o $OUT" > "$OUT.log" 2>&1 || { echo "STEP FAILED $ID (log $OUT.log)"; tail -25 "$OUT.log"; exit 1; }
echo "STEP OK $ID -> $OUT"
