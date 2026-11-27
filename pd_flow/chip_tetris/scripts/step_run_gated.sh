#!/bin/bash
# Run one LibreLane 3.0.14 step standalone in Docker, but only while fewer than MAXC (default 2)
# LibreLane containers run machine-wide (docker ps).  A mkdir lock serializes this script's own
# launches so two local dry runs cannot both pass the check at once.
# usage: step_run_gated.sh <step_id> <config.json> <state_in.json> <outdir>
set -uo pipefail
ID="$1"; CFG="$2"; ST="$3"; OUT="$4"; MAXC="${MAXC:-2}"
PDKV=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee
source /Users/samuelzhang/ttsetup/env.sh
LOCK=/Users/samuelzhang/ttharden/dp_work/.launch.lock
mkdir -p "$OUT"
NAME="dpw_$$_$RANDOM"
while true; do
  # a lock older than 60 s is stale (its holder died between mkdir and rmdir)
  if [ -d "$LOCK" ] && [ $(( $(date +%s) - $(stat -f %m "$LOCK") )) -gt 60 ]; then rmdir "$LOCK" 2>/dev/null; fi
  if mkdir "$LOCK" 2>/dev/null; then
    n=$(docker ps --format '{{.Image}}' | grep -c librelane)
    if [ "$n" -lt "$MAXC" ]; then
      docker run --rm --name "$NAME" -v "$PDKV:$PDKV" -v /Users/samuelzhang/ttharden:/Users/samuelzhang/ttharden -w "$OUT" \
        ghcr.io/librelane/librelane:3.0.14 bash -lc "python3 -m librelane.steps run --id $ID -c $CFG -i $ST -o $OUT" > "$OUT.log" 2>&1 &
      PID=$!
      for i in $(seq 1 40); do docker ps --format '{{.Names}}' | grep -q "$NAME" && break; kill -0 $PID 2>/dev/null || break; sleep 0.25; done
      rmdir "$LOCK"
      wait $PID; RC=$?
      if [ $RC -ne 0 ]; then echo "STEP FAILED $ID (log $OUT.log)"; tail -25 "$OUT.log"; exit 1; fi
      echo "STEP OK $ID -> $OUT"; exit 0
    fi
    rmdir "$LOCK"
  fi
  sleep 3
done
