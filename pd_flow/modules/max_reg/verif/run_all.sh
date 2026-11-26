#!/bin/bash
# max_reg verification contract: reruns every item and writes results.json.
#
# Usage: run_all.sh [--rtl FILE --out DIR] [--gate [--cells DIR] [--lib LIB]] [--jobs J]
#   --rtl FILE  design under test (default: golden pd_flow/baseline/original_rtl/max_reg.v).
#               Later phases pass their implementation here; the contract is unchanged.
#   --out DIR   where results.json, run_all.console.log, logs/ and formal/runs/ go.
#               Required with --rtl; may not be this verif/ directory (the Phase 1 golden
#               evidence lives here and is only written by a run on the golden RTL).
#               Default without --rtl: this directory.
#   --gate      FILE is a gate-level netlist (top module max_reg, GF180 cells). The
#               cells_prep item builds the simulation and Yosys views (SPEC.md section 6).
#   --cells DIR cell Verilog models for --gate (default: GF180 7-track,
#               $PDKV/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/verilog).
#   --lib LIB   liberty for the Yosys/formal models of flop cells (default: the 7-track
#               TT 025C 3V30 liberty).
#   --jobs J    concurrent jobs, at most 8 (default 6). Jobs are single-threaded.
# Exit status: 0 only if every item has ok=true.
#
# Builds run in a space-free temp dir (Verilator makefiles and SBY do not quote paths);
# logs and formal results are written back to the output directory.
set -u
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:$HOME/.local/bin:/opt/homebrew/bin:$PATH"
export PY=/usr/local/bin/python3
export VERIF="$(cd "$(dirname "$0")" && pwd)"
SELF="$VERIF/run_all.sh"

# ------------------------------------------------------------------ one job (internal)
now() { perl -MTime::HiRes=time -e 'printf "%.3f\n", time'; }
record() { # id kind status ok seconds log detail
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" "$5" "$6" "$7" > "$LOGS/items/$1.tsv"
}
T_SIM=900; T_FV=900; T_BUILD=600
NCOV=23   # covers in formal/max_reg_props.sv

job() {
    local id=$1 kind=$2; shift 2
    local log="$LOGS/$id.log" t0 rc st ok det
    t0=$(now)
    cd "$BUILD" || exit 1
    case $kind in
    selftest)
        "$PY" "$VERIF/model/golden_model.py" selftest > "$log" 2>&1; rc=$?
        det=$(grep '^RESULT' "$log" | tail -1)
        if [ $rc -eq 0 ]; then st=pass; ok=true; else st=failed; ok=false; fi ;;
    lint)
        local gopt=""; [ -n "$GATE" ] && gopt="--gate"
        (
            echo "== verilator --lint-only -Wall (simulation view)"
            verilator --lint-only -Wall -Wno-fatal --top-module max_reg max_reg.v 2> lint.vlog; r1=$?
            cat lint.vlog; echo "verilator_rc=$r1"
            "$PY" "$VERIF/lint/check_lint.py" lint.vlog max_reg.v $gopt || r1=1
            echo "== yosys structural check (Yosys view)"
            # proc -noopt: no constant folding before the checks, so a functionally redundant
            # combinational loop is still visible to check (logic loop) and scc. Plain scc
            # (combinational cells only): the M -> compare -> mux -> flop loop is legitimate.
            yosys -q -l lint.ylog -p "read_verilog max_reg_fv.v; hierarchy -check -top max_reg; proc -noopt; flatten; check -assert; scc -select; select -assert-none %; select -clear; select -assert-none t:\$adff* t:\$aldff* t:\$sdff* t:\$dffsr* t:\$dlatch* t:\$adlatch* t:\$sr t:\$mem* t:\$anyinit t:\$_DFF_N* t:\$_DFF_P?_ t:\$_DFFE_N* t:\$_DFFSR* t:\$_SDFF* t:\$_ALDFF* t:\$_DLATCH* t:\$_SR_*; opt_clean; write_json lint.json"; r2=$?
            cat lint.ylog; echo "yosys_rc=$r2"
            echo "== interface / state check"
            "$PY" "$VERIF/lint/check_interface.py" lint.json; r3=$?
            echo "interface_rc=$r3"
            [ $r1 -eq 0 ] && [ $r2 -eq 0 ] && [ $r3 -eq 0 ]
        ) > "$log" 2>&1; rc=$?
        det="$(grep '^RESULT lint' "$log" | tail -1); $(grep '^RESULT interface' "$log" | tail -1)"
        if [ $rc -ne 0 ]; then st=failed; ok=false
        elif grep -q '^RESULT lint .*library=[1-9]' "$log"; then st=pass-with-waiver; ok=true
        else st=pass; ok=true; fi ;;
    build)
        # Gate mode: the unmodified PDK flop wrappers raise IMPLICIT (implicit nets MGM_D0, IQ1),
        # which Verilator makes fatal by default. They are not in the netlist under test (the
        # lint item fails on any netlist warning), so the build uses -Wno-fatal there only.
        local wf=""; [ -n "$GATE" ] && wf="-Wno-fatal"
        timeout $T_BUILD verilator --cc --exe --build --build-jobs 1 -O3 --x-initial unique $wf \
            -CFLAGS -O2 --top-module max_reg --Mdir obj -o sim max_reg.v tb_max_reg.cpp > "$log" 2>&1; rc=$?
        det="obj/sim"
        if [ $rc -eq 0 ] && [ -x obj/sim ]; then st=pass; ok=true
        elif [ $rc -eq 124 ]; then st=timed-out; ok=false; else st=failed; ok=false; fi ;;
    vec)    # random seed: golden-model vectors on Verilator and Icarus
        local k=$1 seed=$2 written v1 v2 c1 c2
        (
            "$PY" "$VERIF/model/golden_model.py" vectors --random "$k" --seed "$seed" --out vec.txt || exit 1
            shasum -a 256 vec.txt
            echo "== verilator"; timeout $T_SIM obj/sim vectors vec.txt; r1=$?
            echo "== icarus"
            iverilog -g2012 -o ivl.vvp tb_vectors.sv max_reg.v && timeout $T_SIM vvp -n ivl.vvp +VEC=vec.txt; r2=$?
            exit $(( r1 == 124 || r2 == 124 ? 124 : (r1 || r2) ))
        ) > "$log" 2>&1; rc=$?
        written=$(sed -n 's/^RESULT vectors written=\([0-9]*\) checked_values=\([0-9]*\).*/\1/p' "$log")
        local known; known=$(sed -n 's/^RESULT vectors written=[0-9]* checked_values=\([0-9]*\).*/\1/p' "$log")
        v1=$(sed -n 's/^RESULT mode=vectors cycles=\([0-9]*\) .*/\1/p' "$log")
        c1=$(sed -n 's/^RESULT mode=vectors .* vec_checked=\([0-9]*\) .*/\1/p' "$log")
        v2=$(sed -n 's/^RESULT sim=icarus vectors=\([0-9]*\) .*/\1/p' "$log")
        c2=$(sed -n 's/^RESULT sim=icarus vectors=[0-9]* checked=\([0-9]*\) .*/\1/p' "$log")
        det="golden_cycles=$written golden_values=$known verilator=$v1/$c1 icarus=$v2/$c2 (cycles/values checked); $(grep '^RESULT mode' "$log" | tail -1)"
        if [ $rc -eq 0 ] && [ -n "$written" ] && [ "$written" = "$v1" ] && [ "$written" = "$v2" ] \
           && [ "$known" = "$c1" ] && [ "$known" = "$c2" ]; then st=pass-sampled; ok=true
        elif [ $rc -eq 124 ]; then st=timed-out; ok=false; else st=failed; ok=false; fi ;;
    sim)    # Verilator in-TB modes: ctrl|free <cycles> <seed>, onestep <hib> <lob>, powerup <seeds>
        timeout $T_SIM obj/sim "$@" > "$log" 2>&1; rc=$?
        det="$(grep '^RESULT_' "$log" | tail -1 | cut -c1-140); $(grep '^RESULT mode' "$log" | tail -1)"
        if [ $rc -eq 0 ]; then
            if [ "$1" = onestep ]; then st=pass-exhaustive-subspace; else st=pass-sampled; fi; ok=true
        elif [ $rc -eq 124 ]; then st=timed-out; ok=false; else st=failed; ok=false; fi ;;
    sby)    # task
        local t=$1 sstat nas ncov nreach want maxstep
        # Each task runs from its own copy of the .sby file in its own directory, so parallel
        # SBY invocations never share SBY's status database.
        rm -rf "fv_$t"; mkdir "fv_$t"
        cp max_reg_fv.v max_reg_props.sv max_reg.sby "fv_$t/"
        cd "fv_$t" || exit 1
        timeout $T_FV "$PY" "$HOME/.local/bin/sby" -f max_reg.sby "$t" > "$log" 2>&1; rc=$?
        sstat=$(awk '{print $1}' "max_reg_$t/status" 2>/dev/null)
        nas=$("$PY" "$VERIF/formal/count_props.py" "max_reg_$t/model/design.json" 2>/dev/null)
        ncov=$(sed -n 's/.*Reached cover statement in step [0-9]* at max_reg_props: \(c_[a-z0-9_]*\).*/\1/p' "$log" | sort -u | wc -l | tr -d ' ')
        maxstep=$(sed -n 's/.*Reached cover statement in step \([0-9]*\) at .*/\1/p' "$log" | sort -n | tail -1)
        nreach=$(grep -ci 'unreached cover' "$log")
        case $t in
        *_step) want="asserts=5 covers=0" ;;
        *_seq)  want="asserts=3 covers=0" ;;
        *_pu)   want="asserts=1 covers=0" ;;
        cover)  want="asserts=9 covers=$NCOV" ;;
        sanity_*) want="asserts=1 covers=0" ;;
        esac
        if [ $rc -eq 124 ]; then st=timed-out; ok=false; det="sby_status=${sstat:-none}; timeout ${T_FV}s"
        elif grep -q 'Traceback' "$log" || { [ "$sstat" != PASS ] && [ "$sstat" != FAIL ]; }; then
            # tool or infrastructure error: no verdict either way (not ok)
            st=inconclusive; ok=false
            det="tool/infrastructure error: sby_status=${sstat:-none}; $(grep -m1 'ERROR\|Error' "$log" | cut -c1-160)"
        else
        case $t in
        prove_*|pdr_*)
            det="sby_status=$sstat $nas (expected $want); $(grep -o 'summary: successful proof[^.]*\|summary: engine_0 (abc pdr) returned PASS' "$log" | head -1)"
            if [ "$sstat" = PASS ] && [ "$nas" = "$want" ]; then st=proven; ok=true
            else st=failed; ok=false; fi ;;
        cover)
            det="sby_status=$sstat $nas reached=$ncov unreached=$nreach max_step=$maxstep depth=10"
            if [ "$sstat" = PASS ] && [ "$ncov" -eq $NCOV ] && [ "$nreach" -eq 0 ] && [ "$nas" = "$want" ]; then st=covered; ok=true
            else st=failed; ok=false; fi ;;
        sanity_*)  # negative control: the wrong property must be refuted with a trace
            local an; an=a_wrong_${t#sanity_}
            det="sby_status=$sstat (expected FAIL) $nas $(grep -o 'failed assertion [^ ]*' "$log" | head -1)"
            if [ "$sstat" = FAIL ] && [ "$nas" = "$want" ] && grep -q "failed assertion max_reg_props.$an" "$log" \
               && ls max_reg_$t/engine_0/trace*.vcd >/dev/null 2>&1; then st=failed-as-expected; ok=true
            else st=failed; ok=false; det="$det; negative control NOT refuted"; fi ;;
        esac
        fi
        mkdir -p "$OUT/formal/runs"
        rm -rf "$OUT/formal/runs/max_reg_$t"
        cp -R "max_reg_$t" "$OUT/formal/runs/" 2>/dev/null ;;
    prep)   # gate-level DUT views: netlist + the cell models it uses
        "$PY" "$VERIF/gate/extract_cells.py" "$DUT" "$CELLS" "$LIB" max_reg.v max_reg_fv.v > "$log" 2>&1; rc=$?
        det="$(grep '^RESULT' "$log" | tail -1); cells=$CELLS; lib=$(basename "$LIB")"
        if [ $rc -eq 0 ]; then st=pass; ok=true; else st=failed; ok=false; fi ;;
    esac
    local t1; t1=$(now)
    record "$id" "$kind" "$st" "$ok" "$(perl -e "printf '%.3f', $t1 - $t0")" "logs/$id.log" "$det"
}

if [ "${1:-}" = __job ]; then shift; job "$@"; exit 0; fi

# ------------------------------------------------------------------ driver
GOLDEN="$(cd "$VERIF/../../../baseline/original_rtl" && pwd)/max_reg.v"
RTL=""; OUT=""; JOBS=6; GATE=""
PDKSC=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0
CELLS="$PDKSC/verilog"
LIB="$PDKSC/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib"
while [ $# -gt 0 ]; do
    case $1 in
    --rtl) RTL=$2; shift 2 ;;
    --out) OUT=$2; shift 2 ;;
    --gate) GATE=1; shift ;;
    --cells) CELLS=$2; shift 2 ;;
    --lib) LIB=$2; shift 2 ;;
    --jobs) JOBS=$2; shift 2 ;;
    *) echo "unknown argument $1" >&2; exit 2 ;;
    esac
done
[ "$JOBS" -gt 8 ] && JOBS=8
if [ -z "$RTL" ]; then
    [ -n "$GATE" ] && { echo "--gate needs --rtl <netlist>" >&2; exit 2; }
    RTL=$GOLDEN; [ -n "$OUT" ] || OUT=$VERIF
else
    [ -n "$OUT" ] || { echo "--rtl needs --out DIR (the Phase 1 evidence in $VERIF is not overwritten)" >&2; exit 2; }
fi
[ -f "$RTL" ] || { echo "RTL not found: $RTL" >&2; exit 2; }
RTL="$(cd "$(dirname "$RTL")" && pwd)/$(basename "$RTL")"
mkdir -p "$OUT" || exit 2
OUT="$(cd "$OUT" && pwd)"
if [ "$OUT" = "$VERIF" ] && [ "$RTL" != "$GOLDEN" -o -n "$GATE" ]; then
    echo "refusing to write results for a non-golden DUT into $VERIF; use --out" >&2; exit 2
fi
if [ -n "$GATE" ]; then
    [ -d "$CELLS" ] || { echo "cell model dir not found: $CELLS" >&2; exit 2; }
    [ -f "$LIB" ] || { echo "liberty not found: $LIB" >&2; exit 2; }
    CELLS="$(cd "$CELLS" && pwd)"
fi
export OUT GATE CELLS LIB DUT="$RTL" NCOV

export LOGS="$OUT/logs"
rm -rf "$LOGS" "$OUT/formal/runs" "$OUT/results.json" "$OUT/run_all.console.log"
mkdir -p "$LOGS/items"
export BUILD="$(mktemp -d "${TMPDIR:-/tmp}/max_reg_verif.XXXXXX")"
# RTL: one file serves simulation and Yosys. Gate: both views are rebuilt by cells_prep.
cp "$RTL" "$BUILD/max_reg.v"
cp "$RTL" "$BUILD/max_reg_fv.v"
cp "$VERIF/sim/tb_max_reg.cpp" "$VERIF/sim/tb_vectors.sv" \
   "$VERIF/formal/max_reg.sby" "$VERIF/formal/max_reg_props.sv" "$BUILD/"
T_START=$(now)
echo "DUT: $RTL${GATE:+ (gate-level netlist, cells $CELLS, flop models from $LIB)}"
echo "output: $OUT"
echo "build dir: $BUILD"

phase() { # name, then job lines "id kind args..." on stdin
    echo "== phase $1"
    tee -a "$LOGS/expected.txt" | tr '\n' '\0' | xargs -0 -P "$JOBS" -n 1 sh -c '"$0" __job $1' "$SELF"
}

FV_TASKS=$(sed -n '/^\[tasks\]/,/^$/p' "$VERIF/formal/max_reg.sby" | awk 'NR>1 && NF {print $1}')
[ -n "$GATE" ] && echo "cells_prep prep" | phase prep
{
    echo "selftest selftest"
    echo "lint lint"
    echo "build build"
} | phase build
{
    echo "vec vec 200000 1"
    echo "sim_ctrl sim ctrl 100000000 0xC0C0"
    echo "sim_free sim free 100000000 0xF00D"
    echo "sim_onestep sim onestep 6 6"
    echo "sim_powerup sim powerup 64"
} | phase sim
for t in $FV_TASKS; do echo "fv_$t sby $t"; done | phase formal

T_END=$(now)
"$PY" - "$LOGS/items" "$OUT/results.json" "$LOGS/expected.txt" "$RTL" "$T_START" "$T_END" "$GATE" "$CELLS" "$LIB" <<'EOF' | tee "$OUT/run_all.console.log"
import csv, glob, hashlib, json, os, re, subprocess, sys
items_dir, out, exp_file, rtl, t0, t1, gate, cells, lib = sys.argv[1:10]
# Standard (AGENT_CONTEXT) label per item, next to the contract's own status.
LABEL = {"proven": "proven", "pass-exhaustive": "pass-exhaustive", "pass-sampled": "pass-sampled",
         "pass-exhaustive-subspace": "pass-sampled",
         "covered": "bounded-pass", "failed-as-expected": "failed", "failed": "failed",
         "timed-out": "timed-out", "inconclusive": "inconclusive", "unsupported": "unsupported",
         "pass": "pass-static", "pass-with-waiver": "pass-static"}
def ver(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, shell=True).stdout.strip().splitlines()[0]
    except Exception:
        return "unknown"
items = []
for p in sorted(glob.glob(os.path.join(items_dir, "*.tsv"))):
    with open(p) as f:
        for row in csv.reader(f, delimiter="\t"):
            iid, kind, st, ok, sec, log, det = (row + [""] * 7)[:7]
            items.append({"id": iid, "kind": kind, "status": st, "ok": ok == "true",
                          "seconds": float(sec or 0), "log": log, "detail": det})
for i in items:
    i["label"] = LABEL.get(i["status"], "inconclusive")
    i["expected_outcome"] = "fail" if i["id"].startswith("fv_sanity") else "pass"
    if i["status"] == "covered":
        i["depth"] = 10
seen = {i["id"] for i in items}
for line in open(exp_file):
    f = line.split()
    if f and f[0] not in seen:
        items.append({"id": f[0], "kind": f[1], "status": "inconclusive", "label": "inconclusive",
                      "expected_outcome": "pass", "ok": False, "seconds": 0.0,
                      "log": f"logs/{f[0]}.log", "detail": "no result recorded (job crashed)"})
order = {"prep": -1, "selftest": 0, "lint": 1, "build": 2, "vec": 3, "sim": 4, "sby": 6}
items.sort(key=lambda i: (order.get(i["kind"], 9), i["id"]))
res = {
    "module": "max_reg",
    "dut": rtl,
    "dut_sha256": hashlib.sha256(open(rtl, "rb").read()).hexdigest(),
    "mode": "gate-level" if gate else "rtl",
    "cells": cells if gate else None,
    "flop_liberty": lib if gate else None,
    "tools": {"verilator": ver("verilator --version"), "iverilog": ver("iverilog -V 2>&1"),
              "yosys": ver("yosys -V"), "z3": ver("z3 --version")},
    "total_seconds": round(float(t1) - float(t0), 3),
    "items_total": len(items),
    "items_ok": sum(i["ok"] for i in items),
    "all_ok": bool(items) and all(i["ok"] for i in items),
    "items": items,
}
json.dump(res, open(out, "w"), indent=2)
for i in items:
    print(f'{i["id"]:<20} {i["status"]:<25} {i["label"]:<14} {i["seconds"]:8.2f}s  {i["detail"][:110]}')
print(f'TOTAL {res["items_ok"]}/{res["items_total"]} ok, all_ok={res["all_ok"]}, {res["total_seconds"]} s')
sys.exit(0 if res["all_ok"] else 1)
EOF
rc=${PIPESTATUS[0]}
rm -rf "$BUILD"
exit $rc
