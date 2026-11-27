#!/bin/bash
# Signoff harden of one whole-chip tetris winner.
# usage: run_signoff.sh <tag> <placement_dir> [r32|firm17] [ref_mirror]   -> /Users/samuelzhang/ttharden/wc_<tag>/runs/wokwi
# ref_mirror defaults to the reference of dplib (env DP_REF's project dir, default wc_ref2).  The mirror is copied
# without runs/; only the copy's src/config.json changes, inserted above the TT "DO NOT CHANGE" block:
#   firm17: MACRO_PLACEMENT_CFG = the placement's macro_placement.cfg (every synthesized cell FIRM at step 17);
#   r32   : MACRO_PLACEMENT_CFG = macro_placement_r32.cfg (cell x for its step-32 master), plus
#           meta {flow: Classic, substituting_steps: {Odb.ManualMacroPlacement: null,
#                 Odb.ManualGlobalPlacement: Odb.ManualMacroPlacement}}: placement is fixed after RepairDesignPostGPL
#           instead of at step 17 (zero-area flow relaxation; repair and upsizing run at the tool's GPL positions).
# src/, tt/ and the PDK of the repo are untouched.  Waits while 2 or more LibreLane containers run machine-wide.
set -euo pipefail
TAG="$1"; PD="$(cd "$2" && pwd)"; MODE="${3:-r32}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REFRUN=$(python3 -c "import sys; sys.path.insert(0, '$HERE'); import dplib; print(dplib.REF)")
SRC="${4:-$(dirname "$(dirname "$REFRUN")")}"
W=/Users/samuelzhang/ttharden/wc_$TAG
source /Users/samuelzhang/ttsetup/env.sh
while [ "$(docker ps --format '{{.Image}}' | grep -c librelane)" -ge 2 ]; do sleep 10; done
mkdir -p "$W"
rsync -a --delete --exclude runs --exclude harden.log --exclude harden.start --exclude harden.end "$SRC/" "$W/"
cp "$PD/placement.json" "$W/placement.json"
if [ "$MODE" = r32 ]; then
  python3 -c "import sys; sys.path.insert(0, '$HERE'); import dplib; dplib.write_r32_cfg('$PD', '$REFRUN', '$PD/macro_placement_r32.cfg')"
  cp "$PD/macro_placement_r32.cfg" "$W/src/macro_placement.cfg"
else
  cp "$PD/macro_placement.cfg" "$W/src/macro_placement.cfg"
fi
python3 - "$W/src/config.json" "$MODE" <<'PY'
import json, sys
path, mode = sys.argv[1:3]
ovr = {"MACRO_PLACEMENT_CFG": "dir::macro_placement.cfg"}
if mode == 'r32':
    ovr["meta"] = {"version": 1, "flow": "Classic",
                   "substituting_steps": {"Odb.ManualMacroPlacement": None, "Odb.ManualGlobalPlacement": "Odb.ManualMacroPlacement"}}
pairs = json.load(open(path), object_pairs_hook=lambda p: p)
out, done = [], False
for k, v in pairs:
    if not done and k == "//" and "DO NOT CHANGE ANYTHING BELOW" in str(v):
        bang = out.pop()
        out.append(("//", f"whole-chip tetris signoff ({mode}): all synthesized cells FIRM (wc_ copy only, not src/)"))
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
echo "done wc_$TAG"
