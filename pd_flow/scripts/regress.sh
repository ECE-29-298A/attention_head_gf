#!/bin/bash
# Full existing regression, suites run in parallel (independent simulators).
# Usage: regress.sh <log_dir>   (run from anywhere; tests use the project's src/)
# Exit status is non-zero if any suite fails. Summary in <log_dir>/SUMMARY.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LOG="${1:?log dir}"; mkdir -p "$LOG"; LOG="$(cd "$LOG" && pwd)"
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:$HOME/.local/bin:/opt/homebrew/bin:$PATH"
PY=/usr/local/bin/python3
cd "$ROOT"

run() { # name, command...
    local name=$1; shift
    local t0=$(date +%s)
    ( "$@" ) > "$LOG/$name.log" 2>&1
    local rc=$?
    echo "$name rc=$rc $(( $(date +%s) - t0 ))s" >> "$LOG/SUMMARY"
}
: > "$LOG/SUMMARY"
run python   $PY -m pytest -q python/test_attention_model.py &
run divider  $PY test/divider/run.py &
run controller $PY test/controller/run.py &
run top      $PY test/top/run.py &
run blocks   bash -c 'cd test/blocks && rm -rf sim_build results.xml && make mac_unit && make max_reg && make exp_lut && ! grep -q "<failure" results.xml' &
run tt_make  bash -c 'cd test && rm -rf sim_build results.xml && make -B && ! grep -q "<failure" results.xml' &
wait
sort "$LOG/SUMMARY" -o "$LOG/SUMMARY"
cat "$LOG/SUMMARY"
! grep -qv " rc=0 " "$LOG/SUMMARY"
