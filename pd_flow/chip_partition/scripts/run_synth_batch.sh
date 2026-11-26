#!/bin/bash
# Run ll_synth_cfg.sh for a list of "tag rtl_dir" pairs, 2 at a time (Docker memory rule).
# Usage: run_synth_batch.sh <tag>:<rtl_dir> ...   (overrides are synth/ovr_<tag>.json)
cd "$(dirname "$0")/.."
run() { t="${1%%:*}"; r="${1#*:}"; scripts/ll_synth_cfg.sh "$r" "$t" "synth/ovr_$t.json" > "logs/llsynth_$t.txt" 2>&1; cat "logs/llsynth_$t.txt" | tail -1; }
set -- "$@"
while [ $# -gt 0 ]; do
  a="$1"; shift; b="${1:-}"; [ -n "$b" ] && shift
  run "$a" & p1=$!
  if [ -n "$b" ]; then run "$b" & p2=$!; wait $p2; fi
  wait $p1
done
