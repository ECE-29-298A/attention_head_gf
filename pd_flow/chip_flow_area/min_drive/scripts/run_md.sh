#!/bin/bash
# Minimum-drive experiment driver (pd_flow/chip_flow_area/min_drive).
# usage: run_md.sh <tag> <overrides.json> [full|<LibreLane step id to stop after>]
#   Makes /Users/samuelzhang/ttharden/md_<tag>, a space-free copy of the golden mirror
#   (/Users/samuelzhang/ttharden/attention_head_gf, runs/ excluded). The copy's src/config.json gets
#   the h2 overrides (../../overrides/h2_k6.json) and then the experiment overrides (an experiment
#   key replaces the h2 key), inserted above the TT "DO NOT CHANGE" block, exactly as run_fx.sh does.
#   A key "__src_files__": {"<name>": "<text>"} writes extra files into the copy's src/ (for a
#   custom PNR_EXCLUDED_CELL_FILE given as "dir::<name>"); it is not written into the config.
#     full    : source ~/ttsetup/env.sh; python tt/tt_tool.py --pdk gf180mcuD --harden
#     <step>  : the same merged config through LibreLane with --to <step> (partial run)
#   Before launching it waits until fewer than 2 LibreLane containers run (machine-wide limit).
set -euo pipefail
TAG="$1"; OVR="$2"; MODE="${3:-full}"
HERE="$(cd "$(dirname "$0")" && pwd)"
H2="$HERE/../../overrides/h2_k6.json"
SRC=/Users/samuelzhang/ttharden/attention_head_gf
W=/Users/samuelzhang/ttharden/md_$TAG
mkdir -p "$W"
rsync -a --delete --exclude runs "$SRC/" "$W/"
python3 - "$W/src" "$H2" "$OVR" <<'PY'
import json, os, sys
src, h2, ovr = sys.argv[1], json.load(open(sys.argv[2])), json.load(open(sys.argv[3]))
files = ovr.pop("__src_files__", {})
for name, text in files.items():
    with open(os.path.join(src, name), "w") as f:
        f.write(text)
merged = dict(h2)
merged.update(ovr)
path = os.path.join(src, "config.json")
pairs = json.load(open(path), object_pairs_hook=lambda p: p)
out, done = [], False
for k, v in pairs:
    if not done and k == "//" and "DO NOT CHANGE ANYTHING BELOW" in str(v):
        bang = out.pop()
        out.append(("//", "chip_flow_area min_drive experiment overrides (md copy only, not src/):"))
        out.extend(merged.items())
        out.append(bang)
        done = True
    if k in merged and k != "//":
        continue
    out.append((k, v))
assert done
with open(path, "w") as f:
    f.write("{\n" + ",\n".join(f"  {json.dumps(k)}: {json.dumps(v)}" for k, v in out) + "\n}\n")
PY
source /Users/samuelzhang/ttsetup/env.sh
# at most 2 LibreLane containers machine-wide (coordinator update; was 1)
n=0
while [ "$(docker ps --format '{{.Image}}' | grep -c librelane)" -ge "${MAX_LL:-2}" ]; do
    [ $((n % 10)) -eq 0 ] && echo "$(date +%T) waiting for running LibreLane container: $(docker ps --format '{{.Names}}' | tr '\n' ' ')"
    n=$((n + 1)); sleep 30
done
echo "$(date +%T) launching $TAG $MODE"
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
        > "$W/partial.log" 2>&1 || { echo "FAILED $TAG $MODE (see $W/partial.log)"; exit 1; }
fi
echo "$(date +%T) done $TAG $MODE"
