#!/bin/bash
# attention_controller verification contract: reruns every item and writes results.json.
# Structure and interface follow the frozen mac_unit / divider contracts.
#
# Usage: run_all.sh [--rtl FILE --out DIR] [--gate [--config P] [--cells DIR] [--lib LIB]]
#                   [--lemmas FILE] [--jobs J]
#   --rtl FILE  design under test (default: golden snapshot/attention_controller.sv). Every
#               submodule (mac_unit, ripple_add, max_reg, exp_lut, divider) that FILE does not
#               define is appended from the frozen snapshot. RTL mode checks OUTPUTS = 8
#               (shipped), 4 and 2.
#   --out DIR   where results.json, run_all.console.log, logs/ and formal/runs/ go. Required
#               with --rtl; may not be this verif/ directory (the golden evidence lives here).
#   --gate      FILE is a gate-level netlist (top module attention_controller with everything
#               flattened into it, GF180 cells, no parameter) of ONE configuration (--config,
#               default 8). cells_prep builds the simulation and Yosys views.
#   --config P  gate mode only: OUTPUTS of the netlist, 2, 4 or 8.
#   --cells DIR / --lib LIB  cell Verilog models / liberty for the flop models (gate mode).
#   --lemmas FILE  optional candidate seq_eq lemma file (assertions over gold.*, cand.* and the
#               read-only observers of formal/ctrl_miter.sv; formal/lemma_prep.py documents the
#               format and its whitelist). Linted (item lemma_lint) and PROVEN, never assumed.
#               Default: formal/golden_self_lemmas.sv for the golden RTL, otherwise none.
#   --jobs J    concurrent jobs, at most 8 (default 3). Jobs are single-threaded.
# Exit status: 0 only if every gating item has ok = true.
#   - equiv_<P> (gating) = eqy_rtl[_<P>] proven OR seq_eq_<P> proven; the two are its non-gating
#     constituents (divider amendment A-1 rule).
#   - Golden-only items (fv_int_*, fv_cov_*, fv_sanity_{mosi,cap,sck}_8) name the golden's
#     internal signals; they run only when the DUT is the golden RTL. A candidate inherits them
#     through equiv_<P> (SPEC.md section 7). fv_top_8 (the TT top around the DUT) runs for every
#     DUT at OUTPUTS = 8.
# Builds run in a space-free temp dir (SBY and EQY do not quote paths). Every check's exit
# status is taken from the check itself, never through a pipe (exp_lut review B1).
set -u
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:$HOME/.local/bin:/opt/homebrew/bin:$PATH"
export PY=/usr/local/bin/python3
export VERIF="$(cd "$(dirname "$0")" && pwd)"
SELF="$VERIF/run_all.sh"
SUBS="mac_unit ripple_add max_reg exp_lut divider"
SUBFILES="mac_unit.v ripple_add.v max_reg.v exp_lut.v divider.v"

# ------------------------------------------------------------------ one job (internal)
now() { perl -MTime::HiRes=time -e 'printf "%.3f\n", time'; }
record() { # id kind status ok seconds log detail
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" "$5" "$6" "$7" > "$LOGS/items/$1.tsv"
}
T_SIM=300; T_FV=900
FORBID='t:$adff* t:$aldff* t:$dffsr* t:$dlatch* t:$adlatch* t:$sr t:$mem* t:$anyinit t:$_DFF_N* t:$_DFFE_N* t:$_DFFSR* t:$_ALDFF* t:$_DLATCH* t:$_SR_*'

want_props() { # expected assert/cover cells per SBY task (vacuity / mis-configuration guard)
    case $1 in
    int_*) echo "asserts=54 covers=0" ;;
    cov_*|sanity_*) echo "asserts=1 covers=0" ;;
    top_8) echo "asserts=4 covers=0" ;;
    esac
}

job() {
    local id=$1 kind=$2; shift 2
    local log="$LOGS/$id.log" t0 rc st ok det
    t0=$(now)
    cd "$BUILD" || exit 1
    case $kind in
    gen)    # e2e vectors from the Python model, per P
        (
            r=0
            for p in $CONFIGS; do "$PY" "$VERIF/sim/gen_vectors.py" --outputs "$p" --out "vec_$p.txt" || r=1; done
            shasum -a 256 vec_*.txt
            exit $r
        ) > "$log" 2>&1; rc=$?
        cp vec_*.txt "$LOGS/" 2>/dev/null
        det="$(grep '^RESULT' "$log" | tr '\n' ';')"
        if [ $rc -eq 0 ]; then st=pass; ok=true; else st=failed; ok=false; fi ;;
    lint)   # P
        local p=$1 gopt="" gparam="" chp="" popt=""
        if [ -n "$GATE" ]; then gopt="--gate"
        else gparam="-GOUTPUTS=$p"; chp="chparam -set OUTPUTS $p attention_controller;"; popt="--params $p"; fi
        (
            echo "== verilator --lint-only -Wall (simulation view, OUTPUTS=$p)"
            verilator --lint-only -Wall -Wno-fatal -Wno-DECLFILENAME $gparam --top-module attention_controller ctrl_dut.v 2> lint_$p.vlog; r1=$?
            cat lint_$p.vlog; echo "verilator_rc=$r1"
            "$PY" "$VERIF/lint/check_lint.py" lint_$p.vlog ctrl_dut.v $gopt || r1=1
            echo "== yosys structural check (Yosys view, read without -formal)"
            # proc -noopt -norom: no constant folding before the checks (a functionally redundant
            # combinational loop stays visible) and the exp_lut table stays logic.
            yosys -q -l lint_$p.ylog -p "read_verilog -sv ctrl_fv.v; $chp hierarchy -check -top attention_controller; proc -noopt -norom; flatten; check -assert; scc -select; select -assert-none %; select -clear; select -assert-none $FORBID; opt_clean; write_json lint_$p.json"; r2=$?
            cat lint_$p.ylog; echo "yosys_rc=$r2"
            echo "== interface / structure / flop-count check"
            "$PY" "$VERIF/lint/check_interface.py" lint_$p.json --outputs $p $popt; r3=$?
            echo "interface_rc=$r3"
            r4=0
            if [ -z "$GATE" ] && [ "$p" = 8 ]; then
                echo "== default parameter value (8): the existing tests instantiate the controller without parameters"
                yosys -q -p "read_verilog -sv ctrl_fv.v; hierarchy -check -top attention_controller; proc -noopt -norom; flatten; opt_clean; write_json lint_default.json"; r4=$?
                "$PY" "$VERIF/lint/check_interface.py" lint_default.json --outputs 8 --params 8 > lint_default.txt || r4=1
                sed 's/^RESULT interface/RESULT default_param/' lint_default.txt
                echo "default_rc=$r4"
            fi
            [ $r1 -eq 0 ] && [ $r2 -eq 0 ] && [ $r3 -eq 0 ] && [ $r4 -eq 0 ]
        ) > "$log" 2>&1; rc=$?
        det="$(grep '^RESULT lint' "$log" | tail -1); $(grep '^RESULT interface' "$log" | tail -1)$(grep '^RESULT default_param' "$log" | tail -1 | sed 's/^/; /')"
        if [ $rc -ne 0 ]; then st=failed; ok=false
        elif grep -q '^RESULT lint .*library=[1-9]\|^RESULT lint .*waived=[1-9]' "$log"; then st=pass-with-waiver; ok=true
        else st=pass; ok=true; fi ;;
    e2e)    # P: end-to-end tapes through the DUT's ports (RTL: Icarus 4-state; gate: Verilator
            # 2-state on the Yosys view (liberty flop models, as the mac_unit contract), random
            # power-up, seeds 1 and 7)
        local p=$1 want sim=icarus n
        want=$(sed -n "s/^RESULT vectors outputs=$p cases=\([0-9]*\) runs=\([0-9]*\)$/cases=\1 runs=\2/p" "$LOGS/gen.log")
        if [ -z "$GATE" ]; then
            (
                iverilog -g2012 -DP_OUTPUTS=$p -o ivl_e2e_$p.vvp "$VERIF/sim/tb_e2e.sv" ctrl_dut.v &&
                timeout $T_SIM vvp -n ivl_e2e_$p.vvp +VECTORS=vec_$p.txt
            ) > "$log" 2>&1; rc=$?
            n=1
        else
            sim=verilator
            (
                verilator --binary --timing -Wno-fatal -Wno-lint -Wno-style -DP_OUTPUTS=$p -DGATE --x-initial unique \
                    --x-assign unique --top-module tb_e2e -Mdir vl_e2e_$p "$VERIF/sim/tb_e2e.sv" ctrl_fv.v > vl_e2e_$p.build.log 2>&1 &&
                timeout $T_SIM ./vl_e2e_$p/Vtb_e2e +verilator+seed+1 +verilator+rand+reset+2 +VECTORS=vec_$p.txt &&
                timeout $T_SIM ./vl_e2e_$p/Vtb_e2e +verilator+seed+7 +verilator+rand+reset+2 +VECTORS=vec_$p.txt
            ) > "$log" 2>&1; rc=$?
            n=2
        fi
        det="sim=$sim $(grep '^RESULT sim' "$log" | tail -1 | sed 's/^RESULT sim //')$( [ -n "$GATE" ] && echo " x2 seeds") (expected $want)"
        if [ $rc -eq 0 ] && [ -n "$want" ] && [ "$(grep -c "^RESULT sim outputs=$p $want errors=0$" "$log")" -eq $n ]; then st=pass-sampled; ok=true
        elif [ $rc -eq 124 ]; then st=timed-out; ok=false; else st=failed; ok=false; fi ;;
    sby)    # sbyfile task : ctrl_int.sby (golden internal) or top.sby
        local f=$1 t=$2 dir sstat nas want efail
        dir="fv_$t"; rm -rf "$dir"; mkdir "$dir"
        case $f in
        ctrl_int)
            sed "s/@P@/${t##*_}/g" "$VERIF/formal/ctrl_int.sby" > "$dir/ctrl_int.sby"
            cp ctrl_int.sv sub.v "$VERIF/formal/ctrl_int_props.vh" "$VERIF/formal/ref_ctrl.v" "$VERIF/formal/cover_top.sv" "$dir/" ;;
        top)
            cp "$VERIF/formal/top.sby" "$VERIF/formal/top_props.vh" "$dir/"
            # a netlist has no parameter: the TT top's OUTPUTS override is dropped for it
            if [ -n "$GATE" ]; then perl -pe 's/attention_controller #\(\.OUTPUTS\(OUTPUTS\)\) core/attention_controller core/' top_fv.v > "$dir/top_fv.v"
            else cp top_fv.v "$dir/top_fv.v"; fi
            cp ctrl_fv.v "$dir/ctrl.v" ;;
        esac
        cd "$dir" || exit 1
        timeout $T_FV "$PY" "$HOME/.local/bin/sby" -f $f.sby "$t" > "$log" 2>&1; rc=$?
        sstat=$(awk '{print $1}' "${f}_$t/status" 2>/dev/null)
        nas=$("$PY" "$VERIF/formal/count_props.py" "${f}_$t/model/design.json" 2>/dev/null)
        want=$(want_props "$t")
        if [ $rc -eq 124 ]; then st=timed-out; ok=false; det="sby_status=${sstat:-none}; timeout ${T_FV}s"
        elif [ "$sstat" = UNKNOWN ]; then
            st=not-proven; ok=false
            det="induction did not close (UNKNOWN): $(grep -o 'failed assertion [^ ]*' "$log" | head -1); $nas"
        elif grep -q 'Traceback' "$log" || { [ "$sstat" != PASS ] && [ "$sstat" != FAIL ]; }; then
            st=inconclusive; ok=false
            det="tool/infrastructure error (or a structure guard rejected the DUT): sby_status=${sstat:-none}; $(grep -m1 'ERROR' "$log" | cut -c1-160)"
        else
            case $t in
            int_*|top_8)
                det="sby_status=$sstat $nas (expected $want); $(grep -o 'summary: successful proof[^.]*' "$log" | head -1)$(grep -o 'failed assertion [^ ]* at [^ ]* step [0-9]*' "$log" | head -1)"
                if [ "$sstat" = PASS ] && [ "$nas" = "$want" ]; then st=proven; ok=true; else st=failed; ok=false; fi ;;
            cov_*)  # the group assertion refuted by abc bmc3 = a witness trace reaching every cover of the group
                det="sby_status=$sstat (expected FAIL = witness) $nas $(grep -o 'failed assertion [^ ]* at [^ ]* step [0-9]*' "$log" | head -1); trace formal/runs/$id/${f}_$t/engine_0/trace.vcd"
                if [ "$sstat" = FAIL ] && [ "$nas" = "$want" ] && grep -q "failed assertion cover_top.ctl.w_group" "$log" \
                   && ls ${f}_$t/engine_0/trace*.vcd >/dev/null 2>&1; then st=covered; ok=true
                else st=failed; ok=false; det="$det; group NOT reached"; fi ;;
            sanity_*)  # negative control: the wrong property must be refuted with a trace
                det="sby_status=$sstat (expected FAIL) $nas $(grep -o 'failed assertion [^ ]*' "$log" | head -1)"
                if [ "$sstat" = FAIL ] && [ "$nas" = "$want" ] && grep -q "failed assertion [a-z_.]*n_" "$log" \
                   && ls ${f}_$t/engine_0/trace*.vcd >/dev/null 2>&1; then st=failed-as-expected; ok=true
                else st=failed; ok=false; det="$det; negative control NOT refuted"; fi ;;
            esac
        fi
        mkdir -p "$OUT/formal/runs/$id"
        cp -R "${f}_$t" "$OUT/formal/runs/$id/" 2>/dev/null ;;
    eqy)    # P
        local p=$1 ed=$id gp=""
        [ -z "$GATE" ] && gp="chparam -set OUTPUTS $p attention_controller"
        rm -rf "$ed"; mkdir "$ed"
        cp gold_rtl.v "$ed/gold.v"; cp ctrl_fv.v "$ed/gate.v"
        sed "/^#/!s/@P@/$p/; /^#/!s/@GATEPARAM@/$gp/" "$VERIF/gate/eqy_rtl.eqy" > "$ed/eq.eqy"
        ( cd "$ed" && timeout $T_FV "$PY" "$HOME/.local/bin/eqy" -f eq.eqy ) > "$log" 2>&1; rc=$?
        local estat np nf nm
        estat=$(grep -o 'DONE ([A-Z]*' "$log" | tail -1 | sed 's/DONE (//')
        np=$(grep -c 'Successfully proved equivalence of partition' "$log")
        nf=$(grep -c 'Failed to prove equivalence of partition' "$log")
        nm=$(grep -vc '^#' "$ed/eq/matched.ids" 2>/dev/null)
        det="eqy_status=${estat:-none} partitions_proved=$np partitions_failed=$nf matched_names=$nm (strategy sat, depth 1, gold = golden RTL at OUTPUTS=$p)"
        if [ $rc -eq 124 ]; then st=timed-out; ok=false
        elif [ "$estat" = PASS ] && [ "$np" -ge 1 ] && [ "$nf" -eq 0 ]; then st=proven; ok=true
        elif [ "$estat" = FAIL ]; then st=failed; ok=false
        else st=inconclusive; ok=false; det="tool/infrastructure error: $det; $(grep -m1 'ERROR' "$log" | cut -c1-120)"; fi
        mkdir -p "$OUT/formal/runs"; rm -rf "$OUT/formal/runs/$ed"; cp -R "$ed" "$OUT/formal/runs/" 2>/dev/null ;;
    lemlint)
        "$PY" "$VERIF/formal/lemma_prep.py" lint "$LEMMAS" > "$log" 2>&1; rc=$?
        det="$(grep '^RESULT' "$log" | tail -1); file=$LEMMAS; $(grep -m2 '^REJECT' "$log" | tr '\n' ' ')"
        if [ $rc -eq 0 ]; then st=pass; ok=true; else st=failed; ok=false; fi ;;
    seq)    # P [sanity]: golden vs DUT miter, reset-anchored (formal/ctrl_miter.sv)
        local p=$1 mode=${2:-} t lf=$LEMMAS nl sstat nas fails defs="-DP_OUTPUTS=$1"
        t=seq_$p; [ "$mode" = sanity ] && { t=sanity_seq_$p; lf=none; defs="$defs -DSANITY_EQ"; }
        rm -rf "$id"; mkdir "$id"
        perl -pe 's/\b(attention_controller|mac_unit|ripple_add|max_reg|exp_lut|divider)\b/gold_$1/g' gold_rtl.v > "$id/gold.v"
        cp ctrl_fv.v "$id/ctrl_dut.v"
        cp "$VERIF/formal/ctrl_miter.sv" "$VERIF/formal/seq_eq.sby" "$VERIF/formal/seq_gold.ys" fv_mode.vh "$id/"
        cd "$id" || exit 1
        echo '// no lemmas' > seq_lemmas.vh; echo '# no lemmas' > seq_lemmas.ys
        (
            echo "== net widths (flattened miter, no lemmas)"
            yosys -q -p "read_verilog -formal -sv $defs ctrl_miter.sv; read_verilog -sv gold.v; read_verilog -sv ctrl_dut.v; hierarchy -top ctrl_miter; proc -norom; flatten; write_json widths.json" || exit 3
            echo "== lemmas: $lf"
            "$PY" "$VERIF/formal/lemma_prep.py" gen "$lf" "$p" widths.json seq_lemmas.vh seq_lemmas.ys || exit 3
            cat seq_lemmas.vh seq_lemmas.ys
            echo "== sby $t"
            timeout $T_FV "$PY" "$HOME/.local/bin/sby" -f seq_eq.sby "$t"
        ) > "$log" 2>&1; rc=$?
        nl=$(sed -n 's/^RESULT lemma_gen .*lemmas=\([0-9]*\) .*/\1/p' "$log")
        sstat=$(awk '{print $1}' "seq_eq_$t/status" 2>/dev/null)
        nas=$("$PY" "$VERIF/formal/count_props.py" "seq_eq_$t/model/design.json" 2>/dev/null)
        fails=$(grep -o 'Assert failed in ctrl_miter: [A-Za-z_0-9]*' "$log" | sed 's/.*: //' | sort -u | tr '\n' ' ')
        if [ $rc -eq 3 ]; then
            st=failed; ok=false; det="lemma file rejected or a referenced net does not exist: $(grep -m2 '^REJECT\|ERROR' "$log" | tr '\n' ' ')"
        elif [ $rc -eq 124 ]; then st=timed-out; ok=false; det="sby_status=${sstat:-none}; timeout ${T_FV}s"
        elif [ "$mode" = sanity ]; then
            det="sby_status=$sstat (expected FAIL) $nas failed: $fails"
            if [ "$sstat" = FAIL ] && [ "$nas" = "asserts=1 covers=0" ] && echo "$fails" | grep -q a_wrong_eq \
               && ls seq_eq_$t/engine_0/trace*.vcd >/dev/null 2>&1; then st=failed-as-expected; ok=true
            else st=failed; ok=false; det="$det; negative control NOT refuted"; fi
        elif [ "$sstat" = PASS ] && [ "$nas" = "asserts=$((2 + ${nl:-0})) covers=0" ]; then
            st=proven; ok=true; det="sby_status=PASS $nas (a_eq + a_obs + $nl lemmas); basecase depth 3 from free independent start states + k-induction; reset-anchored; lemmas=$(basename "$lf")"
        elif [ "$sstat" = FAIL ]; then
            st=failed; ok=false
            det="counterexample: failed $fails; trace formal/runs/$id/seq_eq_$t/engine_0/trace.vcd; lemmas=$(basename "$lf")"
        elif [ "$sstat" = UNKNOWN ]; then
            st=not-proven; ok=false
            det="induction did not close (basecase passed; add or strengthen lemmas): $nas; failed in induction: $fails; lemmas=$(basename "$lf")"
        else
            st=inconclusive; ok=false; det="tool/infrastructure error (or a seq_eq.sby guard rejected the DUT): sby_status=${sstat:-none} $nas; $(grep -m1 'ERROR' "$log" | cut -c1-140)"
        fi
        mkdir -p "$OUT/formal/runs"; rm -rf "$OUT/formal/runs/$id"; cd "$BUILD" && cp -R "$id" "$OUT/formal/runs/" 2>/dev/null ;;
    prep)
        "$PY" "$VERIF/gate/extract_cells.py" "$DUT" "$CELLS" "$LIB" ctrl_dut.v ctrl_fv.v > "$log" 2>&1; rc=$?
        det="$(grep '^RESULT' "$log" | tail -1) cells=$(basename "$CELLS"); lib=$(basename "$LIB")"
        if [ $rc -eq 0 ]; then st=pass; ok=true; else st=failed; ok=false; fi ;;
    esac
    local t1; t1=$(now)
    record "$id" "$kind" "$st" "$ok" "$(perl -e "printf '%.3f', $t1 - $t0")" "logs/$id.log" "$det"
}

if [ "${1:-}" = __job ]; then shift; job "$@"; exit 0; fi

# ------------------------------------------------------------------ driver
SNAP="$(cd "$VERIF/../snapshot" && pwd)"
GOLDEN="$SNAP/attention_controller.sv"
RTL=""; OUT=""; JOBS=3; GATE=""; GCFG=8; LEMMAS=
PDKSC=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0
CELLS="$PDKSC/verilog"
LIB="$PDKSC/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib"
while [ $# -gt 0 ]; do
    case $1 in
    --rtl) RTL=$2; shift 2 ;;
    --out) OUT=$2; shift 2 ;;
    --gate) GATE=1; shift ;;
    --config) GCFG=$2; shift 2 ;;
    --cells) CELLS=$2; shift 2 ;;
    --lib) LIB=$2; shift 2 ;;
    --jobs) JOBS=$2; shift 2 ;;
    --lemmas) LEMMAS=$2; shift 2 ;;
    *) echo "unknown argument $1" >&2; exit 2 ;;
    esac
done
[ "$JOBS" -gt 8 ] && JOBS=8
case $GCFG in 2|4|8) ;; *) echo "--config must be 2, 4 or 8" >&2; exit 2 ;; esac
if [ -z "$RTL" ]; then
    [ -n "$GATE" ] && { echo "--gate needs --rtl <netlist>" >&2; exit 2; }
    RTL=$GOLDEN; [ -n "$OUT" ] || OUT=$VERIF
else
    [ -n "$OUT" ] || { echo "--rtl needs --out DIR (the golden evidence in $VERIF is not overwritten)" >&2; exit 2; }
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
    CONFIGS=$GCFG
else
    CONFIGS="8 4 2"
fi
IS_GOLDEN=""
if [ -z "$GATE" ] && [ "$(shasum -a 256 < "$RTL")" = "$(shasum -a 256 < "$GOLDEN")" ]; then IS_GOLDEN=1; fi
if [ -n "$LEMMAS" ]; then
    [ -f "$LEMMAS" ] || { echo "lemma file not found: $LEMMAS" >&2; exit 2; }
    LEMMAS="$(cd "$(dirname "$LEMMAS")" && pwd)/$(basename "$LEMMAS")"
elif [ -n "$IS_GOLDEN" ]; then
    LEMMAS="$VERIF/formal/golden_self_lemmas.sv"   # golden vs golden self-check
else
    LEMMAS=none
fi
export OUT GATE GCFG CELLS LIB DUT="$RTL" FORBID LEMMAS CONFIGS

export LOGS="$OUT/logs"
rm -rf "$LOGS" "$OUT/formal/runs" "$OUT/results.json" "$OUT/run_all.console.log"
mkdir -p "$LOGS/items"
export BUILD="$(mktemp -d "${TMPDIR:-/tmp}/ctrl_verif.XXXXXX")"
# golden: the snapshot (all six files); DUT: the candidate plus the frozen submodules it lacks
SUB_NOTE=""
for f in attention_controller.sv $SUBFILES; do cat "$SNAP/$f"; done > "$BUILD/gold_rtl.v"
if [ -z "$GATE" ]; then
    cat "$RTL" > "$BUILD/ctrl_dut.v"   # cat, not cp: the snapshot files are read-only
    for m in $SUBS; do
        if ! grep -Eq "^[[:space:]]*module[[:space:]]+$m([^A-Za-z0-9_\$]|\$)" "$RTL"; then
            cat "$SNAP/$m.v" >> "$BUILD/ctrl_dut.v"; SUB_NOTE="$SUB_NOTE $m"
        fi
    done
    cp "$BUILD/ctrl_dut.v" "$BUILD/ctrl_fv.v"
    [ -n "$SUB_NOTE" ] && SUB_NOTE=" + frozen snapshot submodules:$SUB_NOTE"
fi
# golden-internal harness copies (from the snapshot, never from the DUT)
perl -pe 's/^endmodule/`include "ctrl_int_props.vh"\nendmodule/' "$SNAP/attention_controller.sv" > "$BUILD/ctrl_int.sv"
for f in $SUBFILES; do cat "$SNAP/$f"; done > "$BUILD/sub.v"
perl -pe 's/^endmodule/`include "top_props.vh"\nendmodule/' "$SNAP/project.v" > "$BUILD/top_fv.v"
if [ -n "$GATE" ]; then echo '`define GATE' > "$BUILD/fv_mode.vh"; else echo '// RTL mode' > "$BUILD/fv_mode.vh"; fi
T_START=$(now)
echo "DUT: $RTL$SUB_NOTE${GATE:+ (gate-level netlist, OUTPUTS=$GCFG, cells $CELLS, flop models from $LIB)}"
echo "golden RTL: ${IS_GOLDEN:-no} (golden-only internal items ${IS_GOLDEN:+run}${IS_GOLDEN:-skipped})"
echo "configs (OUTPUTS): $CONFIGS"
echo "seq_eq lemmas: $LEMMAS"
echo "output: $OUT"
echo "build dir: $BUILD"

phase() { # name, then job lines "id kind args..." on stdin
    echo "== phase $1"
    tee -a "$LOGS/expected.txt" | tr '\n' '\0' | xargs -0 -P "$JOBS" -n 1 sh -c '"$0" __job $1' "$SELF"
}

INT_TASKS=$(sed -n '/^\[tasks\]/,/^$/p' "$VERIF/formal/ctrl_int.sby" | awk 'NR>1 && NF {print $1}')
[ -n "$GATE" ] && echo "cells_prep prep" | phase prep
{
    echo "gen gen"
    for p in $CONFIGS; do echo "lint_$p lint $p"; done
    [ "$LEMMAS" != none ] && echo "lemma_lint lemlint"
} | phase build
{
    for p in $CONFIGS; do echo "e2e_$p e2e $p"; done
} | phase sim
{
    if [ -n "$IS_GOLDEN" ]; then
        for t in $INT_TASKS; do echo "fv_$t sby ctrl_int $t"; done
    fi
    case " $CONFIGS " in *" 8 "*) echo "fv_top_8 sby top top_8"; [ -n "$IS_GOLDEN" ] && echo "fv_sanity_top_8 sby top sanity_top_8" ;; esac
    if [ -n "$GATE" ]; then echo "eqy_rtl eqy $GCFG"; else for p in $CONFIGS; do echo "eqy_rtl_$p eqy $p"; done; fi
    for p in $CONFIGS; do echo "seq_eq_$p seq $p"; echo "fv_sanity_seq_$p seq $p sanity"; done
} | phase formal

T_END=$(now)
"$PY" - "$LOGS/items" "$OUT/results.json" "$LOGS/expected.txt" "$RTL" "$T_START" "$T_END" "$GATE" "$CELLS" "$LIB" "$GCFG" "$GOLDEN" "$LEMMAS" "$CONFIGS" "$SUB_NOTE" "$IS_GOLDEN" <<'EOF' > "$OUT/run_all.console.log"
import csv, glob, hashlib, json, os, re, subprocess, sys
items_dir, out, exp_file, rtl, t0, t1, gate, cells, lib, gcfg, golden, lemmas, configs, sub_note, is_golden = sys.argv[1:16]
configs = configs.split()
LABEL = {"proven": "proven", "pass-sampled": "pass-sampled", "not-proven": "inconclusive",
         "covered": "bounded-pass", "failed-as-expected": "failed", "failed": "failed",
         "timed-out": "timed-out", "inconclusive": "inconclusive", "unsupported": "unsupported",
         "pass": "pass-static", "pass-with-waiver": "pass-static"}
def ver(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, shell=True).stdout.strip().splitlines()[0]
    except Exception:
        return "unknown"
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
items = []
for p in sorted(glob.glob(os.path.join(items_dir, "*.tsv"))):
    with open(p) as f:
        for row in csv.reader(f, delimiter="\t"):
            iid, kind, st, ok, sec, log, det = (row + [""] * 7)[:7]
            items.append({"id": iid, "kind": kind, "status": st, "ok": ok == "true",
                          "seconds": float(sec or 0), "log": log, "detail": det})
for i in items:
    i["label"] = LABEL.get(i["status"], "inconclusive")
    i["gating"] = True
    i["expected_outcome"] = "fail" if ("sanity" in i["id"] or i["id"].startswith("fv_cov_")) else "pass"
    i["scope"] = "golden-only" if (i["id"].startswith(("fv_int_", "fv_cov_", "fv_sanity_mosi", "fv_sanity_cap", "fv_sanity_sck", "fv_sanity_top"))) else "every-dut"
    if i["status"] == "covered":
        m = re.search(r"step (\d+)", i["detail"])
        i["depth"] = int(m.group(1)) if m else None
seen = {i["id"] for i in items}
for line in open(exp_file):
    f = line.split()
    if f and f[0] not in seen:
        items.append({"id": f[0], "kind": f[1], "status": "inconclusive", "label": "inconclusive",
                      "expected_outcome": "pass", "ok": False, "seconds": 0.0, "gating": True, "scope": "",
                      "log": f"logs/{f[0]}.log", "detail": "no result recorded (job crashed)"})
byid = {i["id"]: i for i in items}
for c in configs:
    e = byid.get("eqy_rtl" if gate else f"eqy_rtl_{c}")
    q = byid.get(f"seq_eq_{c}")
    for x in (e, q):
        if x:
            x["gating"] = False
            x["part_of"] = f"equiv_{c}"
    okk = bool((e and e["ok"]) or (q and q["ok"]))
    items.append({"id": f"equiv_{c}", "kind": "derived", "status": "proven" if okk else "failed",
                  "label": "proven" if okk else "failed", "expected_outcome": "pass", "ok": okk,
                  "gating": True, "scope": "every-dut", "seconds": 0.0, "log": "",
                  "detail": f"eqy_rtl: {e['status'] if e else 'missing'}; seq_eq_{c}: {q['status'] if q else 'missing'} (ok if either is proven)"})
order = {"prep": -1, "gen": 0, "lint": 1, "lemlint": 1, "e2e": 3, "sby": 6, "eqy": 7, "seq": 8, "derived": 9}
items.sort(key=lambda i: (order.get(i["kind"], 9), i["id"]))
res = {
    "module": "attention_controller",
    "dut": rtl, "dut_sha256": sha(rtl), "dut_note": sub_note.strip() or None,
    "dut_is_golden": bool(is_golden), "mode": "gate-level" if gate else "rtl",
    "configs": configs, "config_meaning": "OUTPUTS (results per run); 8 shipped, 4 and 2 legal",
    "seq_eq_lemmas": None if lemmas == "none" else lemmas,
    "seq_eq_lemmas_sha256": None if lemmas == "none" else sha(lemmas),
    "cells": cells if gate else None, "flop_liberty": lib if gate else None,
    "tools": {"iverilog": ver("iverilog -V 2>&1"), "verilator": ver("verilator --version"),
              "yosys": ver("yosys -V"), "z3": ver("z3 --version")},
    "total_seconds": round(float(t1) - float(t0), 3),
    "items_total": len(items), "items_ok": sum(i["ok"] for i in items),
    "gating_total": sum(i["gating"] for i in items),
    "gating_ok": sum(i["ok"] for i in items if i["gating"]),
    "all_ok": bool(items) and all(i["ok"] for i in items if i["gating"]),
    "items": items,
}
json.dump(res, open(out, "w"), indent=2)
for i in items:
    print(f'{i["id"]:<22} {i["status"]:<19} {i["label"]:<13} {"" if i["gating"] else "(non-gating) "}{i["seconds"]:8.2f}s  {i["detail"][:120]}')
print(f'TOTAL {res["gating_ok"]}/{res["gating_total"]} gating ok, all_ok={res["all_ok"]}; {res["total_seconds"]} s')
sys.exit(0 if res["all_ok"] else 1)
EOF
rc=$?   # exit status of the summariser itself, not of a pipe (exp_lut review B1)
cat "$OUT/run_all.console.log"
rm -rf "$BUILD"
exit $rc
