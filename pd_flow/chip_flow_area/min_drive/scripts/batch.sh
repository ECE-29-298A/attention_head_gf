#!/bin/bash
# Run partial screens one after another: run_md.sh <tag> ../overrides/<tag>.json <step>, then the
# post-GRT multi-corner STA proxy (../../scripts/sta_proxy.sh) when the run reached step 43.
# usage: [NOPROXY=1] batch.sh <step> <tag>...   (NOPROXY: skip the proxy, e.g. for runs through step 55)
HERE="$(cd "$(dirname "$0")" && pwd)"
STEP="$1"; shift
for t in "$@"; do
    "$HERE/run_md.sh" "$t" "$HERE/../overrides/$t.json" "$STEP" || { echo "run failed: $t"; continue; }
    W=/Users/samuelzhang/ttharden/md_$t
    if [ -z "${NOPROXY:-}" ] && [ -d "$W/runs/wokwi/43-openroad-stamidpnr-3" ]; then
        while [ "$(docker ps --format "{{.Image}}" | grep -c librelane)" -ge 2 ]; do sleep 20; done
        "$HERE/../../scripts/sta_proxy.sh" "$W" > "$W/sta_proxy.log" 2>&1 && tail -5 "$W/sta_proxy.log"
    fi
    "$HERE/save_evidence.sh" "$t" || true
    echo "$(date +%T) finished $t"
done
