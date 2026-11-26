#!/bin/bash
# Independent golden-vs-mutant miter (SBY prove, depth 1, stateless guard) at N = 12, 16, 22.
# Usage: run_equiv.sh <mutant.v> <outdir>. Prints "<task> <status>" lines.
set -u
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:$HOME/.local/bin:/opt/homebrew/bin:$PATH"
HERE="$(cd "$(dirname "$0")" && pwd)"
G="$HERE/../../../../baseline/original_rtl/ripple_add.v"
W="$(mktemp -d "${TMPDIR:-/tmp}/ra_eq.XXXXXX")"
sed 's/^module ripple_add /module ripple_add_golden /' "$G" > "$W/golden.v"
cp "$1" "$W/dut.v"; cp "$HERE/miter.sv" "$HERE/miter.sby" "$W/"
mkdir -p "$2"
cd "$W"
for t in n12 n16 n22; do
    timeout 600 /usr/local/bin/python3 "$HOME/.local/bin/sby" -f miter.sby $t > "sby_$t.log" 2>&1
    st=$(awk '{print $1}' miter_$t/status 2>/dev/null); [ -n "$st" ] || st=ERROR
    cp "sby_$t.log" "$2/"; [ -f miter_$t/engine_0/trace.vcd ] && cp miter_$t/engine_0/trace.vcd "$2/cex_$t.vcd"
    echo "$t $st"
done
rm -rf "$W"
