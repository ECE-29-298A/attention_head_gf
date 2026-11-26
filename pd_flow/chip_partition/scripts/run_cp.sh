#!/bin/bash
# Integration-pilot driver (Architect A, pd_flow/chip_partition).
# usage: run_cp.sh <tag> <pilot_dir> [full|<LibreLane step id to stop after>]
#   Makes /Users/samuelzhang/ttharden/cpa_<tag>: a space-free copy of the h2 run setup
#   (/Users/samuelzhang/ttharden/fx_h2_k6, runs/ excluded; its src/config.json is the F1/h2 config).
#   Copies <pilot_dir>/{pilot.v,placement.cfg} to src/pilot/, then changes ONLY:
#     user_config.json : VERILOG_FILES = [dir::pilot/pilot.v]          (structural netlist in)
#     config.json      : SYNTH_ELABORATE_ONLY = true                    (no re-synthesis, names kept)
#                        MACRO_PLACEMENT_CFG  = dir::pilot/placement.cfg (every instance FIRM)
#                        + any keys in <pilot_dir>/extra_config.json
#   full   : python tt/tt_tool.py --pdk gf180mcuD --harden   (refuses if another LibreLane runs)
#   <step> : the same merged config through LibreLane with --to <step> (partial run)
set -euo pipefail
TAG="$1"; PDIR="$(cd "$2" && pwd)"; MODE="${3:-full}"
SRC=/Users/samuelzhang/ttharden/fx_h2_k6
W=/Users/samuelzhang/ttharden/cpa_$TAG
if docker ps --format '{{.Image}}' | grep -q librelane; then
  echo "another LibreLane container is running; refusing (one harden at a time)"; docker ps; exit 3
fi
mkdir -p "$W"
rsync -a --delete --exclude runs --exclude harden.log --exclude partial.log "$SRC/" "$W/"
mkdir -p "$W/src/pilot"
cp "$PDIR/pilot.v" "$PDIR/placement.cfg" "$W/src/pilot/"
python3 - "$W/src" "$PDIR" <<'PY'
import json, os, sys
src, pdir = sys.argv[1], sys.argv[2]
uc = json.load(open(f"{src}/user_config.json"))
uc["VERILOG_FILES"] = ["dir::pilot/pilot.v"]
json.dump(uc, open(f"{src}/user_config.json", "w"), indent=2)
ovr = {"SYNTH_ELABORATE_ONLY": True, "MACRO_PLACEMENT_CFG": "dir::pilot/placement.cfg"}
extra = os.path.join(pdir, "extra_config.json")
if os.path.exists(extra):
    ovr.update(json.load(open(extra)))
pairs = json.load(open(f"{src}/config.json"), object_pairs_hook=lambda p: p)
out, done = [], False
for k, v in pairs:
    if not done and k == "//" and "DO NOT CHANGE ANYTHING BELOW" in str(v):
        bang = out.pop()
        out.append(("//", "chip_partition (Architect A) integration pilot overrides (cpa copy only):"))
        out.extend(ovr.items())
        out.append(bang)
        done = True
    if k in ovr and k != "//":
        continue
    out.append((k, v))
assert done
with open(f"{src}/config.json", "w") as f:
    f.write("{\n" + ",\n".join(f"  {json.dumps(k)}: {json.dumps(v)}" for k, v in out) + "\n}\n")
PY
source /Users/samuelzhang/ttsetup/env.sh
cd "$W"
if [ "$MODE" = full ]; then
    python tt/tt_tool.py --pdk gf180mcuD --harden > "$W/harden.log" 2>&1 || { echo "harden FAILED (see $W/harden.log)"; exit 1; }
else
    python3 - <<'PY'
import sys
sys.path.insert(0, "tt")
from config_utils import read_config, write_config, override_config
write_config(override_config(read_config("src/config"), read_config("src/user_config")), "src/config_merged")
PY
    rm -rf runs/wokwi; mkdir -p runs/wokwi
    python -m librelane --pdk-root "$PDK_ROOT" --docker-no-tty --dockerized --pdk gf180mcuD \
        --run-tag wokwi --force-run-dir runs/wokwi --to "$MODE" src/config_merged.json \
        > "$W/partial.log" 2>&1 || { echo "partial run FAILED (see $W/partial.log)"; exit 1; }
fi
echo "done $TAG $MODE"
