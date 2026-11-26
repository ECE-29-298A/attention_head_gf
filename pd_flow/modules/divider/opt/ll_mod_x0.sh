#!/bin/bash
# ll_mod_x0.sh <cand.v> <LD> <CI> <tag>: module-level shipped-flow synthesis (x0 config: md_x0_full
# config_merged.json + pnr_exclude_md.cells) with DESIGN_NAME divider, SYNTH_PARAMETERS
# LATCH_DENOMINATOR=<LD> CHECK_INVALID=<CI>, linter off. Produces the gate netlist for the contract's
# --gate mode. Prints "tag area cells netlist". Run dir /Users/samuelzhang/ttharden/llsynth/dvmod_<tag>.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
BASE=/Users/samuelzhang/ttharden/md_x0_full
source /Users/samuelzhang/ttsetup/env.sh >/dev/null 2>&1
C="$1"; LD=$2; CI=$3; n=$4; W=/Users/samuelzhang/ttharden/llsynth/dvmod_$n
while [ "$(docker ps -q | wc -l)" -ge 2 ]; do sleep 20; done
rm -rf "$W"; mkdir -p "$W/src" "$W/runs/synth"; cp "$C" "$W/src/divider.v"; cp "$BASE/src/pnr_exclude_md.cells" "$W/src/"; ln -s "$BASE/tt" "$W/tt"
python3 - "$BASE/src/config_merged.json" "$W/src/config_merged.json" "$LD" "$CI" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
c.update(DESIGN_NAME="divider", VERILOG_FILES=["dir::divider.v"], RUN_LINTER=0,
         SYNTH_PARAMETERS=[f"LATCH_DENOMINATOR={sys.argv[3]}", f"CHECK_INVALID={sys.argv[4]}"])
json.dump(c, open(sys.argv[2], "w"), indent=1)
PY
(cd "$W" && python -m librelane --docker-no-tty --dockerized --pdk-root "$PDK_ROOT" --pdk gf180mcuD \
    --run-tag synth --force-run-dir runs/synth --to Yosys.Synthesis src/config_merged.json > "$W/librelane.log" 2>&1) \
    || { echo "$n FAILED"; tail -5 "$W/librelane.log"; exit 1; }
mkdir -p "$HERE/gate"; cp "$W"/runs/synth/*-yosys-synthesis/divider.nl.v "$HERE/gate/$n.nl.v"
J=$(ls "$W"/runs/synth/*-yosys-synthesis/reports/stat.json); cp "$J" "$HERE/gate/$n.stat.json"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); t=d.get("design") or next(iter(d["modules"].values())); print(sys.argv[2], t["area"], t["num_cells"], sys.argv[3])' "$J" "$n" "$HERE/gate/$n.nl.v"
