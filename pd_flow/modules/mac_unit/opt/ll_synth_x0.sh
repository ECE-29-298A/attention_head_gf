#!/bin/bash
# Private copy of pd_flow/scripts/ll_synth.sh (mac_unit Agent 3; copied from divider/opt) that uses the SHIPPING x0 config
# (h2 + mux2_1 allowed): config_merged.json and pnr_exclude_md.cells of
# /Users/samuelzhang/ttharden/md_x0_full (resolved: md_x0_full/runs/wokwi/resolved.json; patches
# chip_flow_area/recommended_config.patch + chip_flow_area/min_drive/recommended_config.patch).
# Usage: ll_synth_x0.sh <rtl_dir> <tag> -> prints "tag area_um2 cells"; run dir
#        /Users/samuelzhang/ttharden/llsynth/<tag>/.  Golden reproduces md_x0_full 06-yosys-synthesis
#        (40,725.3504 um2, 1,380 cells, netlist sha256 99daa702...).
set -euo pipefail
RTL="$(cd "$1" && pwd)"; TAG="$2"
BASE=/Users/samuelzhang/ttharden/md_x0_full
W=/Users/samuelzhang/ttharden/llsynth/$TAG
rm -rf "$W"; mkdir -p "$W/src"
cp "$BASE/src/config_merged.json" "$BASE/src/pnr_exclude_md.cells" "$W/src/"
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
