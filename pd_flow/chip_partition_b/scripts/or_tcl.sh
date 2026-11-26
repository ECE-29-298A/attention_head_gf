#!/bin/bash
# Run an OpenROAD Tcl script in the LibreLane image with extra env: or_tcl.sh <script.tcl> VAR=VALUE ...
set -euo pipefail
S="$1"; shift
PDKV=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee
source /Users/samuelzhang/ttsetup/env.sh
EX=""; for kv in "$@"; do EX="$EX -e $kv"; done
docker run --rm $EX -v "$PDKV:$PDKV" -v /Users/samuelzhang/ttharden:/Users/samuelzhang/ttharden -v "$(dirname "$S"):/scr" \
  ghcr.io/librelane/librelane:3.0.14 bash -lc "openroad -exit -no_splash /scr/$(basename "$S")"
