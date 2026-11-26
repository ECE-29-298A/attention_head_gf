#!/bin/bash
# Shipped-flow synthesis area: run LibreLane 3.0.14 (Docker) through Yosys.Synthesis only,
# with the project's exact merged config (AREA 2, 7-track TT), on an RTL directory.
# Usage: ll_synth.sh <rtl_dir> <tag>     -> prints "tag area_um2 cells"; run dir kept in
#        /Users/samuelzhang/ttharden/llsynth/<tag>/ (space-free, Docker-mountable).
# <rtl_dir> must contain the 7 shipped source files (info.yaml source_files).
set -euo pipefail
RTL="$(cd "$1" && pwd)"; TAG="$2"
BASE=/Users/samuelzhang/ttharden/attention_head_gf     # mirror that holds tt/ and config_merged.json
W=/Users/samuelzhang/ttharden/llsynth/$TAG
rm -rf "$W"; mkdir -p "$W/src"
cp "$BASE/src/config_merged.json" "$W/src/"
for f in project.v attention_controller.sv mac_unit.v ripple_add.v max_reg.v exp_lut.v divider.v; do
    cp "$RTL/$f" "$W/src/"
done
ln -s "$BASE/tt" "$W/tt"; mkdir -p "$W/runs/synth"
source /Users/samuelzhang/ttsetup/env.sh
cd "$W"
python -m librelane --docker-no-tty --dockerized --pdk-root "$PDK_ROOT" --pdk gf180mcuD \
    --run-tag synth --force-run-dir runs/synth --to Yosys.Synthesis src/config_merged.json \
    > "$W/librelane.log" 2>&1 || { tail -30 "$W/librelane.log"; exit 1; }
J=$(ls "$W"/runs/synth/*-yosys-synthesis/reports/stat.json)
python3 - "$J" "$TAG" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
top = d.get("design") or next(iter(d["modules"].values()))
print(sys.argv[2], top["area"], top["num_cells"])
PY
