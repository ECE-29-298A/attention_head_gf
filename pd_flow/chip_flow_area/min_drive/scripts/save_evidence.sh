#!/bin/bash
# Copy the evidence of one md run into ../runs/<partial|full>/<tag>/ (small files only) with SHA256SUMS.
# usage: save_evidence.sh <tag>
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TAG="$1"; W=/Users/samuelzhang/ttharden/md_$TAG; R=$W/runs/wokwi
KIND=partial; [ -d "$R/final" ] && ls "$R"/*-checker-lvs >/dev/null 2>&1 && KIND=full
O="$HERE/../runs/$KIND/$TAG"; rm -rf "$O"; mkdir -p "$O"
cp "$W/src/config.json" "$O/config.json"
cp "$R/resolved.json" "$O/" 2>/dev/null || true
[ -f "$W/sta_proxy/proxy.json" ] && cp "$W/sta_proxy/proxy.json" "$O/sta_proxy.json"
# Synthesis netlist: stored only when it differs from h2's (a339bf99..., stored nowhere else in min_drive;
# h2's own synthesis output is reproduced by m0_ctrl). Its hash always goes to synth.nl.v.sha256.
SYN=$(ls "$R"/06-yosys-synthesis/*.nl.v); shasum -a 256 "$SYN" | cut -d' ' -f1 > "$O/synth.nl.v.sha256"
H2SYN=a339bf991497
case "$(cat "$O/synth.nl.v.sha256")" in $H2SYN*) ;; *) gzip -c "$SYN" > "$O/synth.nl.v.gz";; esac
# Post-CTS netlist (the one every census/attribution uses) and the repair and CTS logs.
d=$R/35-openroad-cts; [ -d "$d" ] && gzip -c "$d"/*.nl.v > "$O/35_cts.nl.v.gz"
for s in 32-openroad-repairdesignpostgpl 35-openroad-cts; do
    [ -d "$R/$s" ] && for l in "$R/$s"/openroad-*.log; do gzip -c "$l" > "$O/$(basename "$l").gz"; done
done
last=$(ls -d "$R"/[0-9]*-* | sort -t- -k1,1n | tail -1)
cp "$last/state_out.json" "$O/last_state_out.json" 2>/dev/null || true
[ "$KIND" = full ] && { cp "$R/final/metrics.json" "$O/"; gzip -c "$R"/final/nl/*.nl.v > "$O/final.nl.v.gz"; }
p55=$(ls -d "$R"/*-openroad-stapostpnr 2>/dev/null | head -1) || true
if [ -n "$p55" ]; then
    mkdir -p "$O/stapostpnr"; for c in "$p55"/*/; do cn=$(basename "$c"); [ -f "$c/checks.rpt" ] && cp "$c/checks.rpt" "$O/stapostpnr/$cn.checks.rpt"; done
    cp "$p55/state_out.json" "$O/stapostpnr_state_out.json"
fi
if [ -d "$R/35-openroad-cts" ]; then
    python3 "$HERE/upsize_diff.py" -q "$SYN" "$R"/35-openroad-cts/*.nl.v --json "$O/upsize_diff.json" > /dev/null
    python3 "$HERE/../../scripts/census.py" "$R"/35-openroad-cts/*.nl.v --json "$O/census.json" > /dev/null
fi
(cd "$O" && find . -type f ! -name SHA256SUMS | sort | xargs shasum -a 256 > SHA256SUMS)
echo "saved $TAG -> $O ($(du -sh "$O" | cut -f1))"
