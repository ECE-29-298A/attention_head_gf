#!/bin/bash
# exp_lut verification contract: reruns every item and writes results.json.
#
# Usage: run_all.sh [--rtl FILE --out DIR] [--gate [--registered N] [--cells DIR] [--lib LIB]] [--jobs J]
#   --rtl FILE  design under test (default: golden pd_flow/modules/exp_lut/snapshot/exp_lut.v).
#               Later phases pass their implementation here; the contract is unchanged.
#               RTL mode checks both configurations, REGISTERED = 0 (shipped) and 1.
#   --out DIR   where results.json, run_all.console.log, logs/ and formal/runs/ go.
#               Required with --rtl; may not be this verif/ directory (the Phase 1 golden
#               evidence lives here and is only written by a run on the golden RTL).
#               Default without --rtl: this directory.
#   --gate      FILE is a gate-level netlist (top module exp_lut, GF180 cells, no parameter)
#               of ONE configuration, given by --registered (default 0, the shipped one).
#               The cells_prep item builds the simulation and Yosys views, and the eqy_rtl
#               item proves the netlist equivalent to the golden RTL at that REGISTERED value
#               (SPEC.md section 6).
#   --registered N  gate mode only: the REGISTERED value the netlist was synthesized with (0|1).
#   --cells DIR cell Verilog models for --gate (default: GF180 7-track,
#               $PDKV/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/verilog).
#   --lib LIB   liberty for the Yosys/formal models of flop cells (default: the 7-track
#               TT 025C 3V30 liberty).
#   --jobs J    concurrent jobs, at most 8 (default 3). Jobs are single-threaded.
# Exit status: 0 only if every gating item has ok=true. Items whose id starts with smoke_ are
# non-gating smoke simulations (user decision D9b): reported (smoke_all_ok), never gating.
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
NCOV_R1=10   # covers in formal/exp_lut_props.sv
FORBID='t:$adff* t:$aldff* t:$sdff* t:$dffsr* t:$dlatch* t:$adlatch* t:$sr t:$mem* t:$anyinit t:$_DFF_N* t:$_DFF_P?_ t:$_DFFE_N* t:$_DFFSR* t:$_SDFF* t:$_ALDFF* t:$_DLATCH* t:$_SR_*'

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
    gen)    # golden-model data used by the simulations and the formal harness
        (
            "$PY" "$VERIF/model/golden_model.py" intervals --out iv.txt &&
            "$PY" "$VERIF/model/golden_model.py" vhdr --out ref_table.vh &&
            "$PY" "$VERIF/model/golden_model.py" edges --random 100000 --seed 7 --out edges.txt &&
            "$PY" "$VERIF/model/golden_model.py" vectors --random 200000 --seed 1 --out vec.txt &&
            shasum -a 256 iv.txt ref_table.vh edges.txt vec.txt
        ) > "$log" 2>&1; rc=$?
        cp iv.txt ref_table.vh "$LOGS/" 2>/dev/null
        det="$(grep '^RESULT' "$log" | tr '\n' ';' | sed 's/;$//')"
        if [ $rc -eq 0 ]; then st=pass; ok=true; else st=failed; ok=false; fi ;;
    lint)   # r
        local r=$1 gopt="" gparam="" chp=""
        if [ -n "$GATE" ]; then gopt="--gate"; else gparam="-GREGISTERED=$r"; chp="chparam -set REGISTERED $r exp_lut;"; fi
        (
            echo "== verilator --lint-only -Wall (simulation view, REGISTERED=$r)"
            verilator --lint-only -Wall -Wno-fatal $gparam --top-module exp_lut exp_lut.v 2> lint_r$r.vlog; r1=$?
            cat lint_r$r.vlog; echo "verilator_rc=$r1"
            "$PY" "$VERIF/lint/check_lint.py" lint_r$r.vlog exp_lut.v $gopt --registered $r || r1=1
            echo "== yosys structural check (Yosys view)"
            # proc -noopt: no constant folding before the checks, so a functionally redundant
            # combinational loop is still visible to check (logic loop) and scc; -norom keeps
            # case tables as logic. Plain scc (combinational cells only).
            yosys -q -l lint_r$r.ylog -p "read_verilog exp_lut_fv.v; $chp hierarchy -check -top exp_lut; proc -noopt -norom; flatten; check -assert; scc -select; select -assert-none %; select -clear; select -assert-none $FORBID; opt_clean; write_json lint_r$r.json"; r2=$?
            cat lint_r$r.ylog; echo "yosys_rc=$r2"
            echo "== interface / state check"
            "$PY" "$VERIF/lint/check_interface.py" lint_r$r.json --registered $r; r3=$?
            echo "interface_rc=$r3"
            r4=0
            if [ -z "$GATE" ] && [ "$r" = 1 ]; then
                echo "== default parameter value: the block test instantiates exp_lut without a parameter, so the default must be REGISTERED = 1"
                yosys -q -p "read_verilog exp_lut_fv.v; hierarchy -check -top exp_lut; proc -noopt -norom; flatten; opt_clean; write_json lint_default.json"; r4=$?
                "$PY" "$VERIF/lint/check_interface.py" lint_default.json --registered 1 | sed 's/^RESULT interface/RESULT default_param/' || r4=1
                echo "default_rc=$r4"
            fi
            [ $r1 -eq 0 ] && [ $r2 -eq 0 ] && [ $r3 -eq 0 ] && [ $r4 -eq 0 ]
        ) > "$log" 2>&1; rc=$?
        det="$(grep '^RESULT lint' "$log" | tail -1); $(grep '^RESULT interface' "$log" | tail -1)$(grep '^RESULT default_param' "$log" | tail -1 | sed 's/^/; /')"
        if [ $rc -ne 0 ]; then st=failed; ok=false
        elif grep -q '^RESULT lint .*library=[1-9]\|^RESULT lint .*port_waived=[1-9]' "$log"; then st=pass-with-waiver; ok=true
        else st=pass; ok=true; fi ;;
    build)  # r
        # Gate mode: the unmodified PDK flop wrappers raise IMPLICIT (implicit nets MGM_D0, IQ1),
        # which Verilator makes fatal by default. They are not in the netlist under test (the
        # lint item fails on any netlist warning), so the build uses -Wno-fatal there only.
        local r=$1 wf="" gparam=""
        if [ -n "$GATE" ]; then wf="-Wno-fatal"; else gparam="-GREGISTERED=$r"; fi
        timeout $T_BUILD verilator --cc --exe --build --build-jobs 1 -O3 --x-initial unique $wf $gparam \
            -CFLAGS -O2 --top-module exp_lut --Mdir obj_r$r -o sim exp_lut.v tb_exp_lut.cpp > "$log" 2>&1; rc=$?
        det="obj_r$r/sim"
        if [ $rc -eq 0 ] && [ -x obj_r$r/sim ]; then st=pass; ok=true
        elif [ $rc -eq 124 ]; then st=timed-out; ok=false; else st=failed; ok=false; fi ;;
    sim)    # r mode args... (Verilator)
        local r=$1 m=$2; shift 2
        timeout $T_SIM obj_r$r/sim "$m" "$@" iv.txt > "$log" 2>&1; rc=$?
        det="$(grep '^RESULT_' "$log" | tail -1 | cut -c1-140)$(grep -q '^RESULT_' "$log" && echo '; ')$(grep '^RESULT mode' "$log" | tail -1)"
        if [ $rc -eq 0 ]; then
            st=pass-sampled; ok=true
        elif [ $rc -eq 124 ]; then st=timed-out; ok=false; else st=failed; ok=false; fi ;;
    vec)    # REGISTERED=1 golden vectors on Verilator and Icarus
        local written known v1 c1 v2 c2 gdef=""
        [ -n "$GATE" ] && gdef="-DGATE"
        (
            echo "== verilator"; timeout $T_SIM obj_r1/sim vectors vec.txt iv.txt; r1=$?
            echo "== icarus"
            iverilog -g2012 $gdef -o ivl_vec.vvp tb_vectors.sv exp_lut.v && timeout $T_SIM vvp -n ivl_vec.vvp +VEC=vec.txt; r2=$?
            exit $(( r1 == 124 || r2 == 124 ? 124 : (r1 || r2) ))
        ) > "$log" 2>&1; rc=$?
        written=$(sed -n 's/^RESULT vectors written=\([0-9]*\) .*/\1/p' "$LOGS/gen.log")
        known=$(sed -n 's/^RESULT vectors written=[0-9]* checked_values=\([0-9]*\).*/\1/p' "$LOGS/gen.log")
        v1=$(sed -n 's/^RESULT mode=vectors cycles=\([0-9]*\) .*/\1/p' "$log")
        c1=$(sed -n 's/^RESULT mode=vectors .* values_checked=\([0-9]*\) .*/\1/p' "$log")
        v2=$(sed -n 's/^RESULT sim=icarus vectors=\([0-9]*\) .*/\1/p' "$log")
        c2=$(sed -n 's/^RESULT sim=icarus vectors=[0-9]* checked=\([0-9]*\) .*/\1/p' "$log")
        det="golden_cycles=$written golden_W_values=$known verilator=$v1/$c1 icarus=$v2/$c2 (cycles/W values checked; done checked every cycle)"
        if [ $rc -eq 0 ] && [ -n "$written" ] && [ "$written" = "$v1" ] && [ "$written" = "$v2" ] \
           && [ "$known" = "$c1" ] && [ "$known" = "$c2" ]; then st=pass-sampled; ok=true
        elif [ $rc -eq 124 ]; then st=timed-out; ok=false; else st=failed; ok=false; fi ;;
    edge)   # r: combinational edge cases + 100k fixed-seed spot checks, Verilator and Icarus
        local r=$1 gdef="" n1 n2 want
        [ -n "$GATE" ] && gdef="-DGATE"
        (
            echo "== verilator"; timeout $T_SIM obj_r$r/sim edge$r edges.txt iv.txt; r1=$?
            echo "== icarus (4-state)"
            iverilog -g2012 -DREG=$r $gdef -o ivl_edge_$r.vvp tb_edge.sv exp_lut.v && timeout $T_SIM vvp -n ivl_edge_$r.vvp +EDGES=edges.txt; r2=$?
            exit $(( r1 == 124 || r2 == 124 ? 124 : (r1 || r2) ))
        ) > "$log" 2>&1; rc=$?
        want=$(sed -n 's/^RESULT edges points=\([0-9]*\) .*/\1/p' "$LOGS/gen.log")
        n1=$(sed -n 's/^RESULT mode=edge[01] points=\([0-9]*\) .*/\1/p' "$log")
        n2=$(sed -n 's/^RESULT sim=icarus reg=[01] points=\([0-9]*\) .*/\1/p' "$log")
        det="edge_points=$want verilator: $(grep '^RESULT_EDGE' "$log" | sed 's/^RESULT_EDGE //'); icarus: $(grep '^RESULT sim=icarus' "$log" | sed 's/^RESULT sim=icarus //')"
        if [ $rc -eq 0 ] && [ -n "$want" ] && [ "$want" = "$n1" ] && [ "$want" = "$n2" ]; then st=pass-edge-spot; ok=true
        elif [ $rc -eq 124 ]; then st=timed-out; ok=false; else st=failed; ok=false; fi ;;
    sby)    # task
        local t=$1 sstat nas ncov nreach want maxstep wcov dep
        # Each task runs from its own copy of the .sby file in its own directory, so parallel
        # SBY invocations never share SBY's status database.
        rm -rf "fv_$t"; mkdir "fv_$t"
        cp exp_lut_fv.v exp_lut_props.sv exp_lut.sby ref_table.vh fv_mode.vh "fv_$t/"
        cd "fv_$t" || exit 1
        timeout $T_FV "$PY" "$HOME/.local/bin/sby" -f exp_lut.sby "$t" > "$log" 2>&1; rc=$?
        sstat=$(awk '{print $1}' "exp_lut_$t/status" 2>/dev/null)
        nas=$("$PY" "$VERIF/formal/count_props.py" "exp_lut_$t/model/design.json" 2>/dev/null)
        ncov=$(grep 'Reached cover statement in step' "$log" | sed 's/.*at exp_lut_props: //' | sort -u | wc -l | tr -d ' ')
        maxstep=$(sed -n 's/.*Reached cover statement in step \([0-9]*\) at .*/\1/p' "$log" | sort -n | tail -1)
        nreach=$(grep -ci 'unreached cover' "$log")
        case $t in
        prove_r1|pdr_r1) want="asserts=6 covers=0" ;;
        cover_r1) want="asserts=6 covers=$NCOV_R1"; wcov=$NCOV_R1; dep=10 ;;
        sanity_*) want="asserts=1 covers=0" ;;
        esac
        # an engine counterexample verdict (not "FAIL for induction", which only means the
        # induction step did not close)
        local efail; efail=$(grep -o 'summary: engine_[0-9]* ([^)]*) returned FAIL[^.]*' "$log" | grep -v 'for induction' | head -1)
        if [ $rc -eq 124 ]; then st=timed-out; ok=false; det="sby_status=${sstat:-none}; timeout ${T_FV}s"
        elif [ -n "$efail" ] && [ "$sstat" != FAIL ] && [ "${t#sanity_}" = "$t" ]; then
            # an engine returned FAIL (a real counterexample) but SBY could not replay the
            # trace (abc pdr: "Could not determine aigsmt status") and ends in ERROR: the
            # engine's verdict stands (max_reg review N2b)
            st=failed; ok=false
            det="engine verdict FAIL, trace not replayed: sby_status=${sstat:-none}; ${efail#summary: }; $(grep -m1 'ERROR' "$log" | sed 's/.*ERROR: //' | cut -c1-100)"
        elif [ "$sstat" = UNKNOWN ]; then
            # k-induction did not close: basecase passed, induction step failed. Not a proof
            # and not a tool error (max_reg review N2a).
            st=not-proven; ok=false
            det="induction did not close (UNKNOWN): $(grep -o 'returned [a-zA-Z]* for basecase' "$log" | head -1), $(grep -o 'returned [a-zA-Z]* for induction' "$log" | head -1) at depth 4; $nas"
        elif grep -q 'Traceback' "$log" || { [ "$sstat" != PASS ] && [ "$sstat" != FAIL ]; }; then
            # tool or infrastructure error: no verdict either way (not ok)
            st=inconclusive; ok=false
            det="tool/infrastructure error: sby_status=${sstat:-none}; $(grep -m1 'ERROR\|Error' "$log" | cut -c1-160)"
        else
        case $t in
        prove_r1|pdr_r1)
            det="sby_status=$sstat $nas (expected $want); $(grep -o 'summary: successful proof[^.]*\|summary: engine_0 (abc pdr) returned PASS' "$log" | head -1)"
            if [ "$sstat" = PASS ] && [ "$nas" = "$want" ]; then st=proven; ok=true
            else st=failed; ok=false; fi ;;
        cover_*)
            det="sby_status=$sstat $nas reached=$ncov unreached=$nreach max_step=$maxstep depth=$dep"
            if [ "$sstat" = PASS ] && [ "$ncov" -eq "$wcov" ] && [ "$nreach" -eq 0 ] && [ "$nas" = "$want" ]; then st=covered; ok=true
            else st=failed; ok=false; fi ;;
        sanity_*)  # negative control: the wrong property must be refuted with a trace
            local an; an=$(echo "$t" | sed 's/^sanity_\(.*\)_r[01]$/a_wrong_\1/')
            det="sby_status=$sstat (expected FAIL) $nas $(grep -o 'failed assertion [^ ]*' "$log" | head -1)"
            if [ "$sstat" = FAIL ] && [ "$nas" = "$want" ] && grep -q "failed assertion exp_lut_props.$an" "$log" \
               && ls exp_lut_$t/engine_0/trace*.vcd >/dev/null 2>&1; then st=failed-as-expected; ok=true
            else st=failed; ok=false; det="$det; negative control NOT refuted"; fi ;;
        esac
        fi
        mkdir -p "$OUT/formal/runs"
        rm -rf "$OUT/formal/runs/exp_lut_$t"
        cp -R "exp_lut_$t" "$OUT/formal/runs/" 2>/dev/null ;;
    eqy)    # r: EQY equivalence of the DUT (gate: the netlist's Yosys view) against the golden RTL
        local r=$1 ed=$id gp=""
        [ -z "$GATE" ] && gp="chparam -set REGISTERED $r exp_lut"
        rm -rf "$ed"; mkdir "$ed"
        cp "$GOLDEN" "$ed/gold.v"; cp exp_lut_fv.v "$ed/gate.v"
        sed "s/@REG@/$r/; s/@GATEPARAM@/$gp/" "$VERIF/gate/eqy_rtl.eqy" > "$ed/eq.eqy"
        ( cd "$ed" && timeout $T_FV "$PY" "$HOME/.local/bin/eqy" -f eq.eqy ) > "$log" 2>&1; rc=$?
        local estat np nf
        estat=$(grep -o 'DONE ([A-Z]*' "$log" | tail -1 | sed 's/DONE (//')
        np=$(grep -c 'Successfully proved equivalence of partition' "$log")
        nf=$(grep -c 'Failed to prove equivalence of partition' "$log")
        det="eqy_status=${estat:-none} partitions_proved=$np partitions_failed=$nf (strategy sat, depth 1, gold = golden RTL with REGISTERED=$r)"
        if [ $rc -eq 124 ]; then st=timed-out; ok=false
        elif [ "$estat" = PASS ] && [ "$np" -ge 1 ] && [ "$nf" -eq 0 ]; then st=proven; ok=true
        elif [ "$estat" = FAIL ]; then st=failed; ok=false
        else st=inconclusive; ok=false; det="tool/infrastructure error: $det; $(grep -m1 'ERROR' "$log" | cut -c1-120)"; fi
        mkdir -p "$OUT/formal/runs"; rm -rf "$OUT/formal/runs/$ed"; cp -R "$ed" "$OUT/formal/runs/" 2>/dev/null ;;
    prep)   # gate-level DUT views: netlist + the cell models it uses
        "$PY" "$VERIF/gate/extract_cells.py" "$DUT" "$CELLS" "$LIB" exp_lut.v exp_lut_fv.v > "$log" 2>&1; rc=$?
        det="$(grep '^RESULT' "$log" | tail -1); cells=$CELLS; lib=$(basename "$LIB")"
        if [ $rc -eq 0 ]; then st=pass; ok=true; else st=failed; ok=false; fi ;;
    esac
    local t1; t1=$(now)
    record "$id" "$kind" "$st" "$ok" "$(perl -e "printf '%.3f', $t1 - $t0")" "logs/$id.log" "$det"
}

if [ "${1:-}" = __job ]; then shift; job "$@"; exit 0; fi

# ------------------------------------------------------------------ driver
GOLDEN="$(cd "$VERIF/../snapshot" && pwd)/exp_lut.v"
RTL=""; OUT=""; JOBS=3; GATE=""; GREG=0
PDKSC=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0
CELLS="$PDKSC/verilog"
LIB="$PDKSC/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib"
while [ $# -gt 0 ]; do
    case $1 in
    --rtl) RTL=$2; shift 2 ;;
    --out) OUT=$2; shift 2 ;;
    --gate) GATE=1; shift ;;
    --registered) GREG=$2; shift 2 ;;
    --cells) CELLS=$2; shift 2 ;;
    --lib) LIB=$2; shift 2 ;;
    --jobs) JOBS=$2; shift 2 ;;
    *) echo "unknown argument $1" >&2; exit 2 ;;
    esac
done
[ "$JOBS" -gt 8 ] && JOBS=8
case $GREG in 0|1) ;; *) echo "--registered must be 0 or 1" >&2; exit 2 ;; esac
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
    CONFIGS=$GREG
else
    CONFIGS="0 1"
fi
export OUT GATE GREG CELLS LIB DUT="$RTL" NCOV_R1 GOLDEN FORBID

export LOGS="$OUT/logs"
rm -rf "$LOGS" "$OUT/formal/runs" "$OUT/results.json" "$OUT/run_all.console.log"
mkdir -p "$LOGS/items"
export BUILD="$(mktemp -d "${TMPDIR:-/tmp}/exp_lut_verif.XXXXXX")"
# RTL: one file serves simulation and Yosys. Gate: both views are rebuilt by cells_prep.
cp "$RTL" "$BUILD/exp_lut.v"
cp "$RTL" "$BUILD/exp_lut_fv.v"
cp "$VERIF/sim/tb_exp_lut.cpp" "$VERIF/sim/tb_vectors.sv" "$VERIF/sim/tb_edge.sv" \
   "$VERIF/formal/exp_lut.sby" "$VERIF/formal/exp_lut_props.sv" "$BUILD/"
if [ -n "$GATE" ]; then echo '`define GATE' > "$BUILD/fv_mode.vh"; else echo '// RTL mode' > "$BUILD/fv_mode.vh"; fi
T_START=$(now)
echo "DUT: $RTL${GATE:+ (gate-level netlist, REGISTERED=$GREG, cells $CELLS, flop models from $LIB)}"
echo "output: $OUT"
echo "build dir: $BUILD"

phase() { # name, then job lines "id kind args..." on stdin
    echo "== phase $1"
    tee -a "$LOGS/expected.txt" | tr '\n' '\0' | xargs -0 -P "$JOBS" -n 1 sh -c '"$0" __job $1' "$SELF"
}

FV_TASKS=$(sed -n '/^\[tasks\]/,/^$/p' "$VERIF/formal/exp_lut.sby" | awk 'NR>1 && NF {print $1}')
[ -n "$GATE" ] && echo "cells_prep prep" | phase prep
{
    echo "selftest selftest"
    echo "gen gen"
    for r in $CONFIGS; do echo "lint_r$r lint $r"; echo "build_r$r build $r"; done
} | phase build
{
    for r in $CONFIGS; do
        echo "edge_r$r edge $r"
        if [ "$r" = 1 ]; then   # non-gating smoke (D9b): a few seconds each
            echo "smoke_seq_r1 sim 1 seq 5000000 0x5E01"
            echo "smoke_powerup_r1 sim 1 powerup 64"
            echo "smoke_vec_r1 vec"
        fi
    done
} | phase sim
{
    for t in $FV_TASKS; do
        case $t in *_r0) [ "${CONFIGS#*0}" = "$CONFIGS" ] && continue ;; *_r1) [ "${CONFIGS#*1}" = "$CONFIGS" ] && continue ;; esac
        echo "fv_$t sby $t"
    done
    if [ -n "$GATE" ]; then echo "eqy_rtl eqy $GREG"; else for r in $CONFIGS; do echo "eqy_rtl_r$r eqy $r"; done; fi
} | phase formal

T_END=$(now)
"$PY" - "$LOGS/items" "$OUT/results.json" "$LOGS/expected.txt" "$RTL" "$T_START" "$T_END" "$GATE" "$CELLS" "$LIB" "$GREG" <<'EOF' | tee "$OUT/run_all.console.log"
import csv, glob, hashlib, json, os, re, subprocess, sys
items_dir, out, exp_file, rtl, t0, t1, gate, cells, lib, greg = sys.argv[1:11]
# Standard (AGENT_CONTEXT) label per item, next to the contract's own status.
LABEL = {"proven": "proven", "pass-sampled": "pass-sampled", "not-proven": "inconclusive",
         "covered": "bounded-pass", "failed-as-expected": "failed", "failed": "failed",
         "timed-out": "timed-out", "inconclusive": "inconclusive", "unsupported": "unsupported",
         "pass": "pass-static", "pass-with-waiver": "pass-static", "pass-edge-spot": "pass-sampled"}
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
    i["gating"] = not i["id"].startswith("smoke_")
    i["expected_outcome"] = "fail" if i["id"].startswith("fv_sanity") else "pass"
    if i["status"] == "covered":
        m = re.search(r"depth=(\d+)", i["detail"])
        i["depth"] = int(m.group(1)) if m else None
seen = {i["id"] for i in items}
for line in open(exp_file):
    f = line.split()
    if f and f[0] not in seen:
        items.append({"id": f[0], "kind": f[1], "status": "inconclusive", "label": "inconclusive",
                      "expected_outcome": "pass", "ok": False, "seconds": 0.0,
                      "log": f"logs/{f[0]}.log", "detail": "no result recorded (job crashed)",
                      "gating": not f[0].startswith("smoke_")})
order = {"prep": -1, "selftest": 0, "gen": 0, "lint": 1, "build": 2, "edge": 3, "sim": 4, "vec": 4, "sby": 6, "eqy": 7}
items.sort(key=lambda i: (order.get(i["kind"], 9), i["id"]))
res = {
    "module": "exp_lut",
    "dut": rtl,
    "dut_sha256": hashlib.sha256(open(rtl, "rb").read()).hexdigest(),
    "mode": "gate-level" if gate else "rtl",
    "registered": int(greg) if gate else [0, 1],
    "cells": cells if gate else None,
    "flop_liberty": lib if gate else None,
    "tools": {"verilator": ver("verilator --version"), "iverilog": ver("iverilog -V 2>&1"),
              "yosys": ver("yosys -V"), "z3": ver("z3 --version")},
    "total_seconds": round(float(t1) - float(t0), 3),
    "items_total": len(items),
    "items_ok": sum(i["ok"] for i in items),
    "gating_total": sum(i["gating"] for i in items),
    "gating_ok": sum(i["ok"] for i in items if i["gating"]),
    "all_ok": bool(items) and all(i["ok"] for i in items if i["gating"]),
    "smoke_all_ok": all(i["ok"] for i in items if not i["gating"]),
    "items": items,
}
json.dump(res, open(out, "w"), indent=2)
for i in items:
    print(f'{i["id"]:<22} {i["status"]:<20} {i["label"]:<15} {"" if i["gating"] else "(smoke) "}{i["seconds"]:8.2f}s  {i["detail"][:110]}')
print(f'TOTAL {res["gating_ok"]}/{res["gating_total"]} gating ok, all_ok={res["all_ok"]}; smoke {res["items_ok"] - res["gating_ok"]}/{res["items_total"] - res["gating_total"]} ok (non-gating); {res["total_seconds"]} s')
sys.exit(0 if res["all_ok"] else 1)
EOF
rc=${PIPESTATUS[0]}
rm -rf "$BUILD"
exit $rc
