#!/bin/bash
# run_batch.sh <mode r32|firm17> <tag> [tag ...]: pipeline.py for each placement, two at a time (the container gate
# in step_run_gated.sh keeps <= 2 LibreLane containers machine-wide); one DRYRUN line per tag in logs/<tag>_<mode>.log
cd "$(dirname "$0")/.."
MODE=$1; shift
run() { python3 scripts/pipeline.py placements/$1 $1 --mode $MODE > logs/$1_$MODE.log 2>&1; grep DRYRUN logs/$1_$MODE.log | tail -1 | sed 's#/Users/samuelzhang/ttharden/wc_work/##' | cut -c1-330; }
while [ $# -gt 0 ]; do
  run $1 & [ $# -gt 1 ] && run $2 & wait; shift; [ $# -gt 0 ] && shift
done
