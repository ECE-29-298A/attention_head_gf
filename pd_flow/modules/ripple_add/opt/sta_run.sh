#!/bin/bash
# sta_run.sh <name>...: copy runs/<name>/netlist_n{22,12}.v to a space-free dir, run OpenSTA in
# the LibreLane container at TT 025C 3V30 and SS 125C 3V00, copy logs back to runs/<name>/sta/.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
source /Users/samuelzhang/ttsetup/env.sh
IMG=ghcr.io/librelane/librelane:3.0.14
PDKV=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee
L=$PDKV/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib
W=/Users/samuelzhang/ttharden/ra_opt_sta; rm -rf $W; mkdir -p $W
cp "$HERE/sta.tcl" $W/
for n in "$@"; do mkdir -p $W/$n; cp "$HERE/runs/$n/netlist_n22.v" "$HERE/runs/$n/netlist_n12.v" $W/$n/; done
cat > $W/go.sh <<'EOS'
for d in */; do d=${d%/}; for w in 22 12; do for c in tt_025C_3v30 ss_125C_3v00; do
  LIB=$LDIR/gf180mcu_fd_sc_mcu7t5v0__$c.lib NET=$d/netlist_n$w.v TAG="$d n$w $c" sta -no_init -exit sta.tcl > $d/sta_n${w}_$c.log 2>&1
done; done; done
EOS
docker run --rm -v "$PDKV:$PDKV" -v "$W:$W" -w "$W" -e LDIR=$L $IMG bash -lc 'bash go.sh' >/dev/null
for n in "$@"; do mkdir -p "$HERE/runs/$n/sta"; cp $W/$n/*.log "$HERE/runs/$n/sta/"; grep -h "^RESULT" "$HERE/runs/$n/sta/"*.log; done
