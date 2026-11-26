#!/bin/bash
# Pilot harden: h2 copy + custom placement (FIRM, MACRO_PLACEMENT_CFG) of one block.
# usage: run_pilot.sh <tag> <placement_dir>   -> /Users/samuelzhang/ttharden/cpb_<tag>/runs/wokwi
# The copy is /Users/samuelzhang/ttharden/fx_h2_k6 (h2 = F1 flow config, golden RTL) without runs/;
# only the copy's src/config.json gains MACRO_PLACEMENT_CFG, inserted above the TT "DO NOT CHANGE" block.
set -euo pipefail
TAG="$1"; PD="$(cd "$2" && pwd)"
SRC=/Users/samuelzhang/ttharden/fx_h2_k6
W=/Users/samuelzhang/ttharden/cpb_$TAG
source /Users/samuelzhang/ttsetup/env.sh
if docker ps --format '{{.Image}}' | grep -q librelane; then echo "another LibreLane container is running; not starting"; exit 2; fi
mkdir -p "$W"
rsync -a --delete --exclude runs --exclude harden.log "$SRC/" "$W/"
cp "$PD/macro_placement.cfg" "$W/src/macro_placement.cfg"
python3 - "$W/src/config.json" <<'PY'
import json, sys
path = sys.argv[1]
ovr = {"MACRO_PLACEMENT_CFG": "dir::macro_placement.cfg"}
pairs = json.load(open(path), object_pairs_hook=lambda p: p)
out, done = [], False
for k, v in pairs:
    if not done and k == "//" and "DO NOT CHANGE ANYTHING BELOW" in str(v):
        bang = out.pop()
        out.append(("//", "chip_partition_b pilot: custom placement of one block (cpb copy only, not src/)"))
        out.extend(ovr.items()); out.append(bang); done = True
    if k in ovr: continue
    out.append((k, v))
assert done
open(path, "w").write("{\n" + ",\n".join(f"  {json.dumps(k)}: {json.dumps(v)}" for k, v in out) + "\n}\n")
PY
cd "$W"
date > "$W/harden.start"
python tt/tt_tool.py --pdk gf180mcuD --harden > "$W/harden.log" 2>&1 || echo "HARDEN EXIT $?"
date > "$W/harden.end"
echo "done cpb_$TAG"
