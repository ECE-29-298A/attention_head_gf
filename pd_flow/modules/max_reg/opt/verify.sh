#!/bin/bash
# verify.sh <cand.v> [contract]: Verilator lint (as max_reg.v), EQY vs the golden original
# (SAT, depth 1, M flops matched by name; no assumptions, cutpoints or blackboxes), and with
# 'contract' the frozen contract verif/run_all.sh --rtl <cand> --out runs/<name>/contract.
set -u
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:$HOME/.local/bin:/opt/homebrew/bin:$PATH"
HERE="$(cd "$(dirname "$0")" && pwd)"
C="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"; NAME=$(basename "$C" .v)
D="$HERE/runs/$NAME"; mkdir -p "$D/eqy"
G="$HERE/../../../baseline/original_rtl/max_reg.v"
T="$(mktemp -d "${TMPDIR:-/tmp}/mr_opt.XXXXXX")"
cp "$C" "$T/max_reg.v"
(cd "$T" && verilator --lint-only -Wall --top-module max_reg max_reg.v > lint.log 2>&1; echo "rc=$?" >> lint.log); cp "$T/lint.log" "$D/lint.log"
mkdir "$T/e"; cp "$G" "$T/e/gold.v"; cp "$C" "$T/e/gate.v"; cp "$HERE/eqy_template.eqy" "$T/e/eq.eqy"
(cd "$T/e" && timeout 600 /usr/local/bin/python3 "$HOME/.local/bin/eqy" -f eq.eqy > eqy.log 2>&1)
cp "$T/e/eqy.log" "$T/e/eq.eqy" "$D/eqy/"; cp -R "$T/e/eq/partitions" "$D/eqy/" 2>/dev/null
CR=skipped
if [ "${2:-}" = contract ]; then
    "$HERE/../verif/run_all.sh" --rtl "$C" --out "$D/contract" --jobs 6 > "$D/contract.console.log" 2>&1; CR="rc=$? $(tail -1 "$D/contract.console.log")"
fi
rm -rf "$T"
echo "$NAME lint=$(tail -1 "$D/lint.log") eqy=$(grep -o 'DONE ([A-Z]*' "$D/eqy/eqy.log" | tail -1) proved=$(grep -c 'Successfully proved equivalence of partition' "$D/eqy/eqy.log") unmatched=$(grep -ci 'unmatched' "$D/eqy/eqy.log") contract=$CR"
