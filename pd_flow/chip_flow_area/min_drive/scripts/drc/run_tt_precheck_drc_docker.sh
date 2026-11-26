#!/bin/bash
# Same checks as run_tt_precheck_drc.sh, run inside the LibreLane 3.0.14 image: its KLayout 0.30.7 has
# Ruby 3.3 (the TT-precheck deck uses Ruby >= 3.0 syntax; the host KLayout 0.30.14 embeds Ruby 2.6).
# usage: [TOP=<topcell>] [DECKS=...] [THREADS=n] run_tt_precheck_drc_docker.sh <outdir> <gds>...  (space-free absolute paths)
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
T=/Users/samuelzhang/ttharden
P=$T/md_pdk_tt/ciel/gf180mcu/versions/e8daeda73ca8f5814dbc0b11d1d05802251a3750/gf180mcuD
DRC=$P/libs.tech/klayout/tech/drc/gf180mcu.drc
OUT="$1"; shift; mkdir -p "$OUT" $T/md_drc/shim; cp "$HERE/shim/pmap" $T/md_drc/shim/pmap
cmds="export PATH=$T/md_drc/shim:\$PATH; "
for g in "$@"; do
    b=$(basename "$g" .gds); b=${b%.gds}
    for deck in "${DECKS:-all,-density,-antenna}" antenna; do
        tag=$([ "$deck" = antenna ] && echo antenna || echo drc)
        cmds+="klayout -b -r $DRC -rd input=$g -rd topcell=${TOP:-TOP} -rd variant=gf180mcuD -rd run_mode=deep -rd threads=${THREADS:-1} -rd decks=$deck -rd report=$OUT/$b.$tag.lyrdb > $OUT/$b.$tag.log 2>&1; echo $b $tag rc=\$?; "
    done
done
source /Users/samuelzhang/ttsetup/env.sh
# machine-wide limit: at most 2 containers of the LibreLane image at once (this one counts)
while [ "$(docker ps --format "{{.Image}}" | grep -c librelane)" -ge 2 ]; do sleep 20; done
docker run --rm -v "$T:$T" -w "$OUT" ghcr.io/librelane/librelane:3.0.14 bash -lc "$cmds"
for g in "$@"; do b=$(basename "$g" .gds); b=${b%.gds}; for tag in drc antenna; do
    echo "$b $tag $(python3 "$HERE/lyrdb_summary.py" "$OUT/$b.$tag.lyrdb" 2>&1 | head -1)"; done; done
