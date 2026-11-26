#!/bin/bash
# Chip-level PD area experiment driver (pd_flow/chip_flow_area).
# usage: run_fx.sh <tag> <overrides.json> [full|<LibreLane step id to stop after>]
#   Makes /Users/samuelzhang/ttharden/fx_<tag>, a space-free copy of the golden mirror
#   (/Users/samuelzhang/ttharden/attention_head_gf, runs/ excluded), adds the overrides to the
#   copy's src/config.json only (inserted above the TT "DO NOT CHANGE" block), then
#     full    : source ~/ttsetup/env.sh; python tt/tt_tool.py --pdk gf180mcuD --harden
#     <step>  : the same merged config through LibreLane with --to <step> (partial run)
#   The run lands in fx_<tag>/runs/wokwi.
set -euo pipefail
TAG="$1"; OVR="$2"; MODE="${3:-full}"
SRC=/Users/samuelzhang/ttharden/attention_head_gf
W=/Users/samuelzhang/ttharden/fx_$TAG
mkdir -p "$W"
rsync -a --delete --exclude runs "$SRC/" "$W/"
python3 - "$W/src/config.json" "$OVR" <<'PY'
import json, sys
path, ovr = sys.argv[1], json.load(open(sys.argv[2]))
pairs = json.load(open(path), object_pairs_hook=lambda p: p)
out, done = [], False
for k, v in pairs:
    if not done and k == "//" and "DO NOT CHANGE ANYTHING BELOW" in str(v):
        # the marker block starts one comment line earlier ("!!!!")
        bang = out.pop()
        out.append(("//", "chip_flow_area experiment overrides (fx copy only, not src/):"))
        out.extend(ovr.items())
        out.append(bang)
        done = True
    if k in ovr and k != "//":
        continue  # replaced by the override
    out.append((k, v))
assert done
with open(path, "w") as f:
    f.write("{\n" + ",\n".join(f"  {json.dumps(k)}: {json.dumps(v)}" for k, v in out) + "\n}\n")
PY
source /Users/samuelzhang/ttsetup/env.sh
cd "$W"
if [ "$MODE" = full ]; then
    python tt/tt_tool.py --pdk gf180mcuD --harden > "$W/harden.log" 2>&1
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
        > "$W/partial.log" 2>&1
fi
echo "done $TAG $MODE"
