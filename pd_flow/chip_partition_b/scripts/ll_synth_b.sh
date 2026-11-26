#!/bin/bash
# Architect B: shipped-flow synthesis (LibreLane 3.0.14, Docker, stops after Yosys.Synthesis)
# with the h2/F1 merged config (EXTRA_EXCLUDED_CELLS applied, as in fx_h2_k6), plus optional
# JSON overrides (e.g. SYNTH_HIERARCHY_MODE, SYNTH_KEEP_HIERARCHY_MODULES).
# Usage: ll_synth_b.sh <rtl_dir> <tag> [overrides.json]
#   prints "tag area_um2 cells sha256(netlist)"; run dir /Users/samuelzhang/ttharden/cpb_synth/<tag>/
# Adapted from pd_flow/scripts/ll_synth.sh (which uses the pre-F1 baseline config).
set -euo pipefail
RTL="$(cd "$1" && pwd)"; TAG="$2"; OVR="${3:-}"
[ -n "$OVR" ] && OVR="$(cd "$(dirname "$OVR")" && pwd)/$(basename "$OVR")"
H2=/Users/samuelzhang/ttharden/fx_h2_k6                 # F1 reference copy (config_merged.json)
BASE=/Users/samuelzhang/ttharden/attention_head_gf      # mirror that holds tt/
W=/Users/samuelzhang/ttharden/cpb_synth/$TAG
rm -rf "$W"; mkdir -p "$W/src"
python3 - "$H2/src/config_merged.json" "$OVR" "$W/src/config_merged.json" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
if sys.argv[2]:
    c.update(json.load(open(sys.argv[2])))
json.dump(c, open(sys.argv[3], "w"), indent=1)
PY
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
N=$(ls "$W"/runs/synth/*-yosys-synthesis/*.nl.v)
python3 - "$J" "$TAG" "$N" <<'PY'
import json, sys, hashlib
d = json.load(open(sys.argv[1]))
top = d.get("design") or next(iter(d["modules"].values()))
sha = hashlib.sha256(open(sys.argv[3], "rb").read()).hexdigest()[:16]
print(sys.argv[2], top["area"], top["num_cells"], sha)
PY
