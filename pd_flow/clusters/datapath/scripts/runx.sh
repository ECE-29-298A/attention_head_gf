#!/bin/bash
# screen x0 candidates sequentially through the reservation fixpoint + FIRM dry run: runx.sh tag [tag ...]
cd "$(dirname "$0")/.."
export DP_REF=/Users/samuelzhang/ttharden/md_x0_full/runs/wokwi
for T in "$@"; do python3 scripts/pipeline.py placements/$T $T > logs/$T.log 2>&1; tail -2 logs/$T.log | head -1; done
