#!/bin/bash
# Signoff harden of one datapath-tetris winner on the shipping netlist x0.
# usage: run_signoff.sh <tag> <placement_dir>   -> /Users/samuelzhang/ttharden/dp_<tag>/runs/wokwi
# The copy is /Users/samuelzhang/ttharden/md_x0_full (x0 = h2 flow config + mux2_1 allowed, golden RTL)
# without runs/; only the copy's src/config.json gains MACRO_PLACEMENT_CFG (Architect B's run_pilot.sh
# pattern), inserted above the TT "DO NOT CHANGE" block.  src/, tt/ and the PDK of the repo are untouched.
# Waits (does not start) while 2 or more LibreLane containers run machine-wide.
set -euo pipefail
TAG="$1"; PD="$(cd "$2" && pwd)"
SRC=/Users/samuelzhang/ttharden/md_x0_full
W=/Users/samuelzhang/ttharden/dp_$TAG
source /Users/samuelzhang/ttsetup/env.sh
while [ "$(docker ps --format '{{.Image}}' | grep -c librelane)" -ge 2 ]; do sleep 10; done
mkdir -p "$W"
rsync -a --delete --exclude runs --exclude harden.log --exclude harden.start --exclude harden.end "$SRC/" "$W/"
cp "$PD/macro_placement.cfg" "$W/src/macro_placement.cfg"
cp "$PD/placement.json" "$W/placement.json"
python3 - "$W/src/config.json" <<'PY'
import json, sys
path = sys.argv[1]
ovr = {"MACRO_PLACEMENT_CFG": "dir::macro_placement.cfg"}
pairs = json.load(open(path), object_pairs_hook=lambda p: p)
out, done = [], False
for k, v in pairs:
    if not done and k == "//" and "DO NOT CHANGE ANYTHING BELOW" in str(v):
        bang = out.pop()
        out.append(("//", "datapath tetris signoff: all synthesized cells FIRM (dp_ copy only, not src/)"))
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
echo "done dp_$TAG"
