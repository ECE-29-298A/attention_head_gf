#!/bin/bash
# ll_mod.sh <cand.v>... : module-level shipped-flow synthesis (exploration only). Same LibreLane
# 3.0.14 Yosys.Synthesis step and merged project config as scripts/ll_synth.sh, but with
# DESIGN_NAME exp_lut, SYNTH_PARAMETERS REGISTERED=0 and the linter off. This reproduces the shipped
# mapping (AREA 2 ABC script, no_synth.cells exclusions such as mux2_1) without the whole-chip ABC
# reshuffle. Prints "name area cells". Run dir /Users/samuelzhang/ttharden/llsynth/elmod_<name>.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BASE=/Users/samuelzhang/ttharden/attention_head_gf
source /Users/samuelzhang/ttsetup/env.sh >/dev/null 2>&1
for C in "$@"; do
    n=$(basename "$C" .v); W=/Users/samuelzhang/ttharden/llsynth/elmod_$n
    while [ -n "$(docker ps -q)" ]; do sleep 20; done
    rm -rf "$W"; mkdir -p "$W/src" "$W/runs/synth"; cp "$C" "$W/src/exp_lut.v"; ln -s "$BASE/tt" "$W/tt"
    python3 - "$BASE/src/config_merged.json" "$W/src/config_merged.json" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
c.update(DESIGN_NAME="exp_lut", VERILOG_FILES=["dir::exp_lut.v"], SYNTH_PARAMETERS=["REGISTERED=0"], RUN_LINTER=0)
json.dump(c, open(sys.argv[2], "w"), indent=1)
PY
    (cd "$W" && python -m librelane --docker-no-tty --dockerized --pdk-root "$PDK_ROOT" --pdk gf180mcuD \
        --run-tag synth --force-run-dir runs/synth --to Yosys.Synthesis src/config_merged.json > "$W/librelane.log" 2>&1) \
        || { echo "$n FAILED"; tail -5 "$W/librelane.log"; continue; }
    J=$(ls "$W"/runs/synth/*-yosys-synthesis/reports/stat.json)
    mkdir -p "$HERE/shipped_flow/module"; cp "$J" "$HERE/shipped_flow/module/$n.stat.json"
    cp "$W"/runs/synth/*-yosys-synthesis/exp_lut.nl.v "$HERE/shipped_flow/module/$n.nl.v" 2>/dev/null
    python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); t=d.get("design") or next(iter(d["modules"].values())); print(sys.argv[2], t["area"], t["num_cells"])' "$J" "$n"
done
