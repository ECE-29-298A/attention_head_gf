#!/bin/bash
# EQY (SAT strategy) golden vs <mutant.v> at N = 12 and 22. Prints "<N> <PASS|FAIL|ERROR>".
set -u
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:$HOME/.local/bin:/opt/homebrew/bin:$PATH"
HERE="$(cd "$(dirname "$0")" && pwd)"
G="$HERE/../../../../baseline/original_rtl/ripple_add.v"
mkdir -p "$2"
for n in 12 22; do
    W="$(mktemp -d "${TMPDIR:-/tmp}/ra_eqy.XXXXXX")"
    cp "$G" "$W/golden.v"; cp "$1" "$W/dut.v"
    sed "s/@N@/$n/g" "$HERE/eqy_template.eqy" > "$W/eq.eqy"
    (cd "$W" && timeout 600 /usr/local/bin/python3 "$HOME/.local/bin/eqy" -f eq.eqy > eqy.log 2>&1)
    st=$(grep -o 'DONE ([A-Z]*' "$W/eqy.log" | tail -1 | sed 's/DONE (//'); [ -n "$st" ] || st=ERROR
    cp "$W/eqy.log" "$2/eqy_n$n.log"; echo "n$n $st"; rm -rf "$W"
done
