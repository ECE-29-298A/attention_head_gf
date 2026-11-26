#!/bin/bash
# Run sta_power.tcl on every explore/netlists/*.v at TT 025C 3V30 and SS 125C 3V00 (container).
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
source /Users/samuelzhang/ttsetup/env.sh
IMG=ghcr.io/librelane/librelane:3.0.14
PDKV=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee
L=$PDKV/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib
W=/Users/samuelzhang/ttharden/ra_explore_sta; rm -rf $W; mkdir -p $W/out
cp "$HERE/sta_power.tcl" $W/; cp "$HERE"/netlists/*.v $W/
cat > $W/go.sh <<'EOS'
for f in *.v; do b=${f%.v}; for c in tt_025C_3v30 ss_125C_3v00; do
  LIB=$LDIR/gf180mcu_fd_sc_mcu7t5v0__$c.lib NET=$f TAG="$b $c" sta -no_init -exit sta_power.tcl > out/${b}_$c.log 2>&1
done; done
EOS
docker run --rm -v "$PDKV:$PDKV" -v "$W:$W" -w "$W" -e LDIR=$L $IMG bash -lc 'bash go.sh' >/dev/null
mkdir -p "$HERE/sta"; cp $W/out/*.log "$HERE/sta/"
grep -h "^RESULT\|^Total" "$HERE"/sta/*.log
