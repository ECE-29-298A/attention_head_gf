#!/bin/bash
# x0 candidate generator wrapper: genx.sh <tag> [extra gen_tetris args...]
# base config = the x0 analog of the best h2 recipe (repair + crit weights, flops frozen)
cd "$(dirname "$0")/.."
export DP_REF=/Users/samuelzhang/ttharden/md_x0_full/runs/wokwi
TAG=$1; shift
python3 scripts/gen_tetris.py --out placements/$TAG --iters 300000 --weights repair \
  --repair-from baseline/x0_area_classes.json ${REPAIR_EXTRA} --K 4 --K2 30 --hpwl-thr 60 \
  --crit baseline/x0_crit.json --freeze-flops "$@" > logs/gen_$TAG.log 2>&1
tail -1 logs/gen_$TAG.log
