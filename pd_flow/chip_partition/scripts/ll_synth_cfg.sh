#!/bin/bash
# Shipped-flow synthesis (LibreLane 3.0.14, Docker, stops after Yosys.Synthesis) under the
# h2 reference config (F1: fx_h2_k6 src/config_merged.json, incl. EXTRA_EXCLUDED_CELLS),
# with optional JSON overrides (e.g. SYNTH_HIERARCHY_MODE, SYNTH_KEEP_HIERARCHY_MODULES,
# VERILOG_FILES for restructured RTL variants).
# Usage: ll_synth_cfg.sh <rtl_dir> <tag> [overrides.json]
#   -> prints "tag area_um2 cells sha256(netlist)"; run dir /Users/samuelzhang/ttharden/cpa_llsynth/<tag>/
# <rtl_dir> holds the Verilog files named in VERILOG_FILES (default: the 7 shipped files).
# Architect A (pd_flow/chip_partition). Adapted from pd_flow/scripts/ll_synth.sh.
set -euo pipefail
RTL="$(cd "$1" && pwd)"; TAG="$2"; OVR="${3:-}"
H2=/Users/samuelzhang/ttharden/fx_h2_k6
W=/Users/samuelzhang/ttharden/cpa_llsynth/$TAG
rm -rf "$W"; mkdir -p "$W/src"
python3 - "$H2/src/config_merged.json" "$OVR" "$W/src/config_merged.json" "$RTL" "$W/src" <<'PY'
import json, sys, shutil, os
base, ovr, out, rtl, dst = sys.argv[1:6]
cfg = json.load(open(base))
if ovr:
    cfg.update(json.load(open(ovr)))
for f in cfg["VERILOG_FILES"]:
    name = f.replace("dir::", "")
    shutil.copy(os.path.join(rtl, name), os.path.join(dst, name))
json.dump(cfg, open(out, "w"), indent=1)
PY
ln -s "$H2/tt" "$W/tt"; mkdir -p "$W/runs/synth"
source /Users/samuelzhang/ttsetup/env.sh
cd "$W"
python -m librelane --docker-no-tty --dockerized --pdk-root "$PDK_ROOT" --pdk gf180mcuD \
    --run-tag synth --force-run-dir runs/synth --to Yosys.Synthesis src/config_merged.json \
    > "$W/librelane.log" 2>&1 || { tail -30 "$W/librelane.log"; exit 1; }
D=$(ls -d "$W"/runs/synth/*-yosys-synthesis)
python3 - "$D" "$TAG" <<'PY'
import json, sys, glob, hashlib
d = sys.argv[1]
st = json.load(open(d + "/reports/stat.json"))
top = st.get("design") or next(iter(st["modules"].values()))
nl = glob.glob(d + "/*.nl.v")[0]
print(sys.argv[2], top["area"], top["num_cells"], hashlib.sha256(open(nl, "rb").read()).hexdigest()[:16])
PY
