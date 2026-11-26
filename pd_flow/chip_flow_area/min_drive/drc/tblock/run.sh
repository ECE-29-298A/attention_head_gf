#!/bin/bash
# Harden the mux2_1 routed DRC test block (LibreLane 3.0.14 Classic flow, gf180mcuD, dockerized).
set -uo pipefail
source /Users/samuelzhang/ttsetup/env.sh
cd /Users/samuelzhang/ttharden/md_tblock
while [ "$(docker ps --format '{{.Image}}' | grep -c librelane)" -ge 2 ]; do sleep 20; done
echo "$(date +%T) launching tblock"
rm -rf runs/tb; mkdir -p runs/tb
python -m librelane --pdk-root "$PDK_ROOT" --docker-no-tty --dockerized --pdk gf180mcuD \
    --run-tag tb --force-run-dir runs/tb src/config.json > harden.log 2>&1
echo "$(date +%T) done tblock rc=$?"
