#!/bin/bash
# Agent 2: exhaustive sweep of a GF180 netlist of exp_lut against the exact reference
# (simulation view: netlist + PDK Verilog models incl. UDP flops, via max_reg's extract_cells.py).
# Usage: run_ref_gate.sh <netlist.v> <REGISTERED> <outdir>
set -u
export PATH="/opt/homebrew/bin:$PATH"
HERE="$(cd "$(dirname "$0")" && pwd)"
NL="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"; R=$2
OUT="$3"; mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"
PDKSC=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0
XC="$HERE/../../../max_reg/verif/gate/extract_cells.py"
T="$(mktemp -d "${TMPDIR:-/tmp}/el_refg.XXXXXX")"
/usr/local/bin/python3 "$XC" "$NL" "$PDKSC/verilog" "$PDKSC/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib" "$T/exp_lut.v" "$T/fv.v" > "$OUT/xc.log" 2>&1 \
  || { echo "extract_cells FAIL"; exit 2; }
cp "$HERE/exhaustive_sweep.cpp" "$HERE/ref_thresholds.h" "$T/"
( cd "$T" && verilator --cc --exe --build -O2 -Wno-fatal -Wno-lint -Wno-style --timing -CFLAGS "-O2 -DREGISTERED=$R -I$T" \
    --Mdir obj --top-module exp_lut exp_lut.v exhaustive_sweep.cpp > "$OUT/build.log" 2>&1 ) || { echo "build FAIL"; exit 2; }
( cd "$T" && ./obj/Vexp_lut > "$OUT/sweep.json" 2> "$OUT/sweep.err" ); r=$?
echo "gate sweep R=$R rc=$r $(cat "$OUT/sweep.json") $(head -2 "$OUT/sweep.err" | tr '\n' ' ')"
rm -rf "$T"; exit $r
