#!/bin/bash
# wait_then.sh <cmd...>: wait until no LibreLane container has been running for two checks 15 s apart, then run cmd.
source /Users/samuelzhang/ttsetup/env.sh
free=0
while [ $free -lt 2 ]; do
  if docker ps --format '{{.Image}}' | grep -q librelane; then free=0; else free=$((free+1)); fi
  [ $free -lt 2 ] && sleep 15
done
echo "machine free at $(date)"; "$@"
