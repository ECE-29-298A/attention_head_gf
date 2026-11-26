#!/bin/bash
# Post-GRT multi-corner STA proxy for a partial run: re-runs LibreLane's own OpenROAD.STAMidPNR
# step (global-routing parasitics, scripts/openroad/sta/corner.tcl) standalone on the input
# state of step 43 (after antenna repair), once per corner, by overriding DEFAULT_CORNER in a
# copy of that step's config.json. Nothing in the run is modified; outputs go to <run>/../sta_proxy/.
# usage: sta_proxy.sh <fx dir> [corners...]
set -euo pipefail
FX="$1"; shift
CORNERS="${*:-max_ss_125C_3v00 nom_ss_125C_3v00 max_tt_025C_3v30 max_ff_n40C_3v60 min_ff_n40C_3v60}"
S=$(ls -d "$FX"/runs/wokwi/43-openroad-stamidpnr-3)
O="$FX/sta_proxy"; rm -rf "$O"; mkdir -p "$O"
PDKV=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee
for c in $CORNERS; do
    python3 - "$S/config.json" "$O/cfg_$c.json" "$c" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); d["DEFAULT_CORNER"] = sys.argv[3]
json.dump(d, open(sys.argv[2], "w"), indent=1)
PY
done
source /Users/samuelzhang/ttsetup/env.sh
docker run --rm -v "$PDKV:$PDKV" -v "$FX:$FX" -w "$FX" ghcr.io/librelane/librelane:3.0.14 bash -lc "
for c in $CORNERS; do
  python3 -m librelane.steps run --id OpenROAD.STAMidPNR -c $O/cfg_\$c.json -i $S/state_in.json -o $O/\$c > $O/\$c.log 2>&1 || echo FAIL \$c
done"
python3 - "$O" $CORNERS <<'PY'
import json, os, sys
o = sys.argv[1]; res = {}
for c in sys.argv[2:]:
    p = os.path.join(o, c, "or_metrics_out.json")
    if not os.path.exists(p):
        print(c, "no metrics"); continue
    m = json.load(open(p))
    g = lambda k: m.get(f"{k}__corner:{c}")
    res[c] = {"setup_ws": g("timing__setup__ws"), "hold_ws": g("timing__hold__ws"),
              "slew": g("design__max_slew_violation__count"), "cap": g("design__max_cap_violation__count"),
              "fanout": g("design__max_fanout_violation__count"), "power": g("power__total")}
    r = res[c]
    print(f"{c:18s} setup {r['setup_ws']:8.3f} hold {r['hold_ws']:7.3f} slew/cap/fanout {r['slew']}/{r['cap']}/{r['fanout']}")
json.dump(res, open(os.path.join(o, "proxy.json"), "w"), indent=1)
PY
