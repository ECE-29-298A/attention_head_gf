#!/bin/bash
# divider verification contract: reruns every item and writes results.json.
#
# Usage: run_all.sh [--rtl FILE --out DIR] [--gate [--config CC] [--cells DIR] [--lib LIB]]
#                   [--lemmas FILE] [--jobs J]
#   --rtl FILE  design under test (default: golden pd_flow/modules/divider/snapshot/divider.v).
#               Later phases pass their implementation here; the contract is unchanged.
#               RTL mode checks both configurations: 00 (LATCH_DENOMINATOR = 0,
#               CHECK_INVALID = 0, shipped) and 11 (the defaults).
#   --out DIR   where results.json, run_all.console.log, logs/ and formal/runs/ go.
#               Required with --rtl; may not be this verif/ directory (the Phase 1 golden
#               evidence lives here and is only written by a run on the golden RTL).
#   --gate      FILE is a gate-level netlist (top module divider, GF180 cells, no parameter)
#               of ONE configuration, given by --config (default 00, the shipped one).
#               cells_prep builds the simulation and Yosys views; eqy_rtl proves the netlist
#               equivalent to the golden RTL at that configuration (SPEC.md section 6).
#   --config CC gate mode only: 00 or 11 (LATCH_DENOMINATOR, CHECK_INVALID of the netlist).
#   --cells DIR cell Verilog models for --gate (default: GF180 7-track).
#   --lib LIB   liberty for the Yosys/formal models of flop cells (default: 7-track TT 025C 3V30).
#   --lemmas FILE  optional candidate-supplied seq_eq lemma file (assertions over gold.* and
#               cand.*; formal/lemma_prep.py documents the format). It is linted (item
#               lemma_lint; any assume/restrict/anyconst/anyseq/force/initial... rejects it)
#               and every lemma is PROVEN with the port equality, never assumed. Its SHA-256
#               is recorded in results.json. Default: formal/golden_self_lemmas.sv when the DUT
#               is the golden RTL, otherwise none.
#   --jobs J    concurrent jobs, at most 8 (default 3). Jobs are single-threaded.
# Exit status: 0 only if every gating item has ok = true.
#   - Equivalence with the golden (amendment A-1): the gating item equiv_<c> is ok if
#     eqy_rtl[_<c>] is proven OR seq_eq_<c> is proven (inconclusive / not-proven = fail);
#     those two are its non-gating constituents.
#   - A white-box fv_result_* proof that reports `unsupported` (a non-golden DUT without the
#     golden's register names) is non-gating: the candidate's result correctness then follows
#     from equiv_<c> plus the golden's fv_result_<c> (SPEC section 4).
#
# Builds run in a space-free temp dir (SBY and EQY do not quote paths); logs and formal
# results are written back to the output directory. Every check's exit status is taken from
# the check itself, never through a pipe (exp_lut review B1).
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
T_SIM=600; T_FV=900
FORBID='t:$adff* t:$aldff* t:$sdff* t:$dffsr* t:$dlatch* t:$adlatch* t:$sr t:$mem* t:$anyinit t:$_DFF_N* t:$_DFF_P?_ t:$_DFFE_N* t:$_DFFSR* t:$_SDFF* t:$_ALDFF* t:$_DLATCH* t:$_SR_*'
WBNAMES='w:state w:step w:quotient w:remainder_value w:negative'
WB11NAMES='w:g_divisor.saved_divisor w:invalid_r'

# expected assert/cover cells per SBY task (vacuity / mis-configuration guard)
want_props() {
    case $1 in
    proto_00|pdr_proto_00|proto_11|pdr_proto_11) echo "asserts=6 covers=0" ;;
    result_00) echo "asserts=16 covers=0" ;;
    result_11) echo "asserts=18 covers=0" ;;
    cover_00) echo "asserts=7 covers=14" ;;
    cover_11) echo "asserts=7 covers=15" ;;
    sanity_pu_00) echo "asserts=1 covers=0" ;;
    sanity_lat_11) echo "asserts=6 covers=0" ;;
    sanity_round_*|sanity_stab_00) echo "asserts=7 covers=0" ;;
    sanity_seq_*) echo "asserts=1 covers=0" ;;
    esac
}

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
    gen)    # golden-model edge-case and spot-check points used by refcheck and edge_*
        (
            "$PY" "$VERIF/model/golden_model.py" edges --random 4000 --seed 7 --out edges.txt &&
            shasum -a 256 edges.txt
        ) > "$log" 2>&1; rc=$?
        cp edges.txt "$LOGS/" 2>/dev/null
        det="$(grep '^RESULT' "$log" | tail -1)"
        if [ $rc -eq 0 ]; then st=pass; ok=true; else st=failed; ok=false; fi ;;
    lint)   # cc
        local c=$1 ld=${1:0:1} ci=${1:1:1} gopt="" gparam="" chp="" popt=""
        if [ -n "$GATE" ]; then gopt="--gate"
        else gparam="-GLATCH_DENOMINATOR=$ld -GCHECK_INVALID=$ci"
             chp="chparam -set LATCH_DENOMINATOR $ld divider; chparam -set CHECK_INVALID $ci divider;"
             popt="--params $ld $ci"; fi
        (
            echo "== verilator --lint-only -Wall (simulation view, config $c)"
            verilator --lint-only -Wall -Wno-fatal $gparam --top-module divider divider.v 2> lint_$c.vlog; r1=$?
            cat lint_$c.vlog; echo "verilator_rc=$r1"
            "$PY" "$VERIF/lint/check_lint.py" lint_$c.vlog divider.v $gopt || r1=1
            echo "== yosys structural check (Yosys view)"
            # proc -noopt: no constant folding before the checks, so a functionally redundant
            # combinational loop is still visible to check and scc.
            yosys -q -l lint_$c.ylog -p "read_verilog divider_fv.v; $chp hierarchy -check -top divider; proc -noopt; flatten; check -assert; scc -select; select -assert-none %; select -clear; select -assert-none $FORBID; opt_clean; write_json lint_$c.json"; r2=$?
            cat lint_$c.ylog; echo "yosys_rc=$r2"
            echo "== interface / structure check"
            "$PY" "$VERIF/lint/check_interface.py" lint_$c.json $popt; r3=$?
            echo "interface_rc=$r3"
            r4=0
            if [ -z "$GATE" ] && [ "$c" = 11 ]; then
                echo "== default parameter values: test/divider instantiates divider without parameters, so the defaults must be 1/1"
                yosys -q -p "read_verilog divider_fv.v; hierarchy -check -top divider; proc -noopt; flatten; opt_clean; write_json lint_default.json"; r4=$?
                # exit status from the check itself, then the copy for the log (review B1)
                "$PY" "$VERIF/lint/check_interface.py" lint_default.json --params 1 1 > lint_default.txt || r4=1
                sed 's/^RESULT interface/RESULT default_param/' lint_default.txt
                echo "default_rc=$r4"
            fi
            [ $r1 -eq 0 ] && [ $r2 -eq 0 ] && [ $r3 -eq 0 ] && [ $r4 -eq 0 ]
        ) > "$log" 2>&1; rc=$?
        det="$(grep '^RESULT lint' "$log" | tail -1); $(grep '^RESULT interface' "$log" | tail -1)$(grep '^RESULT default_param' "$log" | tail -1 | sed 's/^/; /')"
        if [ $rc -ne 0 ]; then st=failed; ok=false
        elif grep -q '^RESULT lint .*library=[1-9]\|^RESULT lint .*waived=[1-9]' "$log"; then st=pass-with-waiver; ok=true
        else st=pass; ok=true; fi ;;
    refcheck)  # the formal reference against the Python model on every edge point
        local want n
        (
            iverilog -g2012 -o ivl_ref.vvp "$VERIF/sim/tb_ref.sv" ref_divider_seq.v &&
            timeout $T_SIM vvp -n ivl_ref.vvp +EDGES=edges.txt
        ) > "$log" 2>&1; rc=$?
        want=$(sed -n 's/^RESULT edges points=\([0-9]*\) .*/\1/p' "$LOGS/gen.log")
        n=$(sed -n 's/^RESULT refcheck points=\([0-9]*\) .*/\1/p' "$log")
        det="$(grep '^RESULT refcheck' "$log" | tail -1) (expected points=$want)"
        if [ $rc -eq 0 ] && [ -n "$want" ] && [ "$want" = "$n" ]; then st=pass; ok=true
        elif [ $rc -eq 124 ]; then st=timed-out; ok=false; else st=failed; ok=false; fi ;;
    edge)   # cc: edge cases + spot checks through the DUT, Icarus 4-state
        local c=$1 defs="" want n
        [ "$c" = 11 ] && defs="-DP11"
        [ -n "$GATE" ] && defs="$defs -DGATE"
        (
            iverilog -g2012 $defs -o ivl_edge_$c.vvp "$VERIF/sim/tb_edge.sv" divider.v &&
            timeout $T_SIM vvp -n ivl_edge_$c.vvp +EDGES=edges.txt
        ) > "$log" 2>&1; rc=$?
        if [ "$c" = 11 ]; then want=$(sed -n 's/^RESULT edges points=\([0-9]*\) .*/\1/p' "$LOGS/gen.log")
        else want=$(sed -n 's/^RESULT edges .* in_domain_00=\([0-9]*\) .*/\1/p' "$LOGS/gen.log"); fi
        n=$(sed -n 's/^RESULT sim=icarus cfg=[0-9]* points=\([0-9]*\) .*/\1/p' "$log")
        det="$(grep '^RESULT sim=icarus' "$log" | tail -1 | sed 's/^RESULT sim=icarus //') (expected points=$want)"
        if [ $rc -eq 0 ] && [ -n "$want" ] && [ "$want" = "$n" ]; then st=pass-edge-spot; ok=true
        elif [ $rc -eq 124 ]; then st=timed-out; ok=false; else st=failed; ok=false; fi ;;
    sby)    # task
        local t=$1 sstat nas ncov nreach want wcov="" dep="" efail
        rm -rf "fv_$t"; mkdir "fv_$t"
        cp divider_fv.v divider_props.sv ref_divider_seq.v divider.sby fv_mode.vh "fv_$t/"
        cd "fv_$t" || exit 1
        if [ "${t#result_}" != "$t" ]; then
            # white-box lemmas need the golden's register names
            local names="$WBNAMES" chp="chparam -set LATCH_DENOMINATOR ${t: -2:1} divider; chparam -set CHECK_INVALID ${t: -1} divider;"
            [ "${t: -2}" = 11 ] && names="$names $WB11NAMES"
            local sel=""; for w in $names; do sel="$sel select -assert-min 1 $w;"; done
            if ! yosys -q -p "read_verilog divider_fv.v; $chp hierarchy -top divider; proc; $sel" > "$log.precheck" 2>&1; then
                cat "$log.precheck" > "$log"
                record "$id" "$kind" unsupported false "$(perl -e "printf '%.3f', $(now) - $t0")" "logs/$id.log" \
                    "white-box lemma names ($names) not in the DUT: golden characterization only; candidate result correctness rests on eqy_rtl (SPEC 4)"
                return
            fi
            rm -f "$log.precheck"
        fi
        timeout $T_FV "$PY" "$HOME/.local/bin/sby" -f divider.sby "$t" > "$log" 2>&1; rc=$?
        sstat=$(awk '{print $1}' "divider_$t/status" 2>/dev/null)
        nas=$("$PY" "$VERIF/formal/count_props.py" "divider_$t/model/design.json" 2>/dev/null)
        ncov=$(grep 'Reached cover statement' "$log" | sed 's/.*at divider_props: //' | sort -u | wc -l | tr -d ' ')
        nreach=$(grep -ci 'unreached cover' "$log")
        want=$(want_props "$t")
        case $t in cover_00) wcov=14; dep=30 ;; cover_11) wcov=15; dep=30 ;; esac
        efail=$(grep -o 'summary: engine_[0-9]* ([^)]*) returned FAIL[^.]*' "$log" | grep -v 'for induction' | head -1)
        if [ $rc -eq 124 ]; then st=timed-out; ok=false; det="sby_status=${sstat:-none}; timeout ${T_FV}s"
        elif [ -n "$efail" ] && [ "$sstat" != FAIL ] && [ "${t#sanity_}" = "$t" ]; then
            # an engine counterexample verdict SBY could not replay (abc pdr, status ERROR)
            st=failed; ok=false
            det="engine verdict FAIL, trace not replayed: sby_status=${sstat:-none}; ${efail#summary: }"
        elif [ "$sstat" = UNKNOWN ]; then
            # k-induction did not close: basecase passed, induction failed. Not a proof, not a
            # counterexample, not a tool error (max_reg review N2a).
            st=not-proven; ok=false
            det="induction did not close (UNKNOWN): $(grep -o 'returned [a-zA-Z]* for basecase' "$log" | head -1), $(grep -o 'returned [a-zA-Z]* for induction' "$log" | head -1); $nas"
        elif grep -q 'Traceback' "$log" || { [ "$sstat" != PASS ] && [ "$sstat" != FAIL ]; }; then
            st=inconclusive; ok=false
            det="tool/infrastructure error: sby_status=${sstat:-none}; $(grep -m1 'ERROR\|Error' "$log" | cut -c1-160)"
        else
            case $t in
            proto_*|pdr_proto_*|result_*)
                det="sby_status=$sstat $nas (expected $want); $(grep -o 'summary: successful proof[^.]*\|summary: engine_0 (abc pdr) returned PASS' "$log" | head -1)"
                if [ "$sstat" = PASS ] && [ "$nas" = "$want" ]; then st=proven; ok=true
                else st=failed; ok=false; fi ;;
            cover_*)
                det="sby_status=$sstat $nas reached=$ncov unreached=$nreach depth=$dep (expected $want)"
                if [ "$sstat" = PASS ] && [ "$ncov" -eq "$wcov" ] && [ "$nreach" -eq 0 ] && [ "$nas" = "$want" ]; then st=covered; ok=true
                else st=failed; ok=false; fi ;;
            sanity_*)  # negative control: the wrong property must be refuted with a trace
                local an; an=$(echo "$t" | sed 's/^sanity_\(.*\)_[01][01]$/a_wrong_\1/')
                det="sby_status=$sstat (expected FAIL) $nas $(grep -o 'failed assertion [^ ]*' "$log" | head -1)"
                if [ "$sstat" = FAIL ] && [ "$nas" = "$want" ] && grep -q "failed assertion divider_props.$an" "$log" \
                   && ls divider_$t/engine_0/trace*.vcd >/dev/null 2>&1; then st=failed-as-expected; ok=true
                else st=failed; ok=false; det="$det; negative control NOT refuted"; fi ;;
            esac
        fi
        mkdir -p "$OUT/formal/runs"
        rm -rf "$OUT/formal/runs/divider_$t"
        cp -R "divider_$t" "$OUT/formal/runs/" 2>/dev/null ;;
    eqy)    # cc: EQY of the DUT (gate: the netlist's Yosys view) against the golden RTL
        local c=$1 ld=${1:0:1} ci=${1:1:1} ed=$id gp=""
        [ -z "$GATE" ] && gp="chparam -set LATCH_DENOMINATOR $ld divider\nchparam -set CHECK_INVALID $ci divider"
        rm -rf "$ed"; mkdir "$ed"
        cp "$GOLDEN" "$ed/gold.v"; cp divider_fv.v "$ed/gate.v"
        sed "/^#/!s/@LD@/$ld/; /^#/!s/@CI@/$ci/; /^#/!s/@GATEPARAM@/$gp/" "$VERIF/gate/eqy_rtl.eqy" > "$ed/eq.eqy"
        ( cd "$ed" && timeout $T_FV "$PY" "$HOME/.local/bin/eqy" -f eq.eqy ) > "$log" 2>&1; rc=$?
        local estat np nf nm
        estat=$(grep -o 'DONE ([A-Z]*' "$log" | tail -1 | sed 's/DONE (//')
        np=$(grep -c 'Successfully proved equivalence of partition' "$log")
        nf=$(grep -c 'Failed to prove equivalence of partition' "$log")
        nm=$(grep -vc '^#' "$ed/eq/matched.ids" 2>/dev/null)
        det="eqy_status=${estat:-none} partitions_proved=$np partitions_failed=$nf matched_names=$nm (strategy sat, depth 1, merged partition, gold = golden RTL at $c)"
        if [ $rc -eq 124 ]; then st=timed-out; ok=false
        elif [ "$estat" = PASS ] && [ "$np" -ge 1 ] && [ "$nf" -eq 0 ]; then st=proven; ok=true
        elif [ "$estat" = FAIL ]; then st=failed; ok=false
        else st=inconclusive; ok=false; det="tool/infrastructure error: $det; $(grep -m1 'ERROR' "$log" | cut -c1-120)"; fi
        mkdir -p "$OUT/formal/runs"; rm -rf "$OUT/formal/runs/$ed"; cp -R "$ed" "$OUT/formal/runs/" 2>/dev/null ;;
    lemlint)  # candidate lemma file: assertions only
        "$PY" "$VERIF/formal/lemma_prep.py" lint "$LEMMAS" > "$log" 2>&1; rc=$?
        det="$(grep '^RESULT' "$log" | tail -1); file=$LEMMAS; $(grep -m2 '^REJECT' "$log" | tr '\n' ' ')"
        if [ $rc -eq 0 ]; then st=pass; ok=true; else st=failed; ok=false; fi ;;
    seq)    # cc [sanity]: golden vs DUT miter from the cycle-0 reset (formal/divider_miter.sv)
        local c=$1 mode=${2:-} t defs="" lf=$LEMMAS nl sstat nas fails
        t=seq_$c; [ "$mode" = sanity ] && { t=sanity_seq_$c; lf=none; }
        [ "$c" = 11 ] && defs="-DP11"
        [ "$mode" = sanity ] && defs="$defs -DSANITY_EQ"
        rm -rf "$id"; mkdir "$id"
        sed 's/^module divider #/module divider_gold #/' "$GOLDEN" > "$id/gold.v"
        cp divider_fv.v divider_miter.sv seq_eq.sby fv_mode.vh "$id/"
        cd "$id" || exit 1
        echo '// no lemmas' > seq_lemmas.vh; echo '# no lemmas' > seq_lemmas.ys
        (
            echo "== net widths (flattened miter, no lemmas)"
            yosys -q -p "read_verilog -formal -sv $defs divider_miter.sv; read_verilog -formal gold.v; read_verilog -formal divider_fv.v; hierarchy -top divider_miter; proc; flatten; write_json widths.json" || exit 3
            echo "== lemmas: $lf"
            "$PY" "$VERIF/formal/lemma_prep.py" gen "$lf" "$c" widths.json seq_lemmas.vh seq_lemmas.ys || exit 3
            cat seq_lemmas.vh seq_lemmas.ys
            echo "== sby $t"
            timeout $T_FV "$PY" "$HOME/.local/bin/sby" -f seq_eq.sby "$t"
        ) > "$log" 2>&1; rc=$?
        nl=$(sed -n 's/^RESULT lemma_gen .*lemmas=\([0-9]*\) .*/\1/p' "$log")
        sstat=$(awk '{print $1}' "seq_eq_$t/status" 2>/dev/null)
        nas=$("$PY" "$VERIF/formal/count_props.py" "seq_eq_$t/model/design.json" 2>/dev/null)
        fails=$(grep -o 'Assert failed in divider_miter: [A-Za-z_0-9]*' "$log" | sed 's/.*: //' | sort -u | tr '\n' ' ')
        if [ $rc -eq 3 ]; then
            st=failed; ok=false; det="lemma file rejected or a referenced net does not exist: $(grep -m2 '^REJECT\|ERROR' "$log" | tr '\n' ' ')"
        elif [ $rc -eq 124 ]; then st=timed-out; ok=false; det="sby_status=${sstat:-none}; timeout ${T_FV}s"
        elif [ "$mode" = sanity ]; then
            det="sby_status=$sstat (expected FAIL) $nas failed: $fails"
            if [ "$sstat" = FAIL ] && [ "$nas" = "asserts=1 covers=0" ] && echo "$fails" | grep -q a_wrong_eq \
               && ls seq_eq_$t/engine_0/trace*.vcd >/dev/null 2>&1; then st=failed-as-expected; ok=true
            else st=failed; ok=false; det="$det; negative control NOT refuted"; fi
        elif [ "$sstat" = PASS ] && [ "$nas" = "asserts=$((1 + ${nl:-0})) covers=0" ]; then
            st=proven; ok=true; det="sby_status=PASS $nas (a_eq + $nl lemmas); basecase depth 30 from the cycle-0 reset + k-induction; lemmas=$(basename "$lf")"
        elif [ "$sstat" = FAIL ]; then
            st=failed; ok=false
            det="counterexample: failed $fails($(grep -o 'returned FAIL for basecase' "$log" | head -1)); trace formal/runs/$id/seq_eq_$t/engine_0/trace.vcd; lemmas=$(basename "$lf")"
        elif [ "$sstat" = UNKNOWN ]; then
            st=not-proven; ok=false
            det="induction did not close (basecase depth 30 passed; add or strengthen lemmas): $nas; lemmas=$(basename "$lf")"
        else
            st=inconclusive; ok=false; det="tool/infrastructure error: sby_status=${sstat:-none} $nas; $(grep -m1 'ERROR' "$log" | cut -c1-140)"
        fi
        mkdir -p "$OUT/formal/runs"; rm -rf "$OUT/formal/runs/$id"; cd "$BUILD" && cp -R "$id" "$OUT/formal/runs/" 2>/dev/null ;;
    prep)   # gate-level DUT views: netlist + the cell models it uses
        "$PY" "$VERIF/gate/extract_cells.py" "$DUT" "$CELLS" "$LIB" divider.v divider_fv.v > "$log" 2>&1; rc=$?
        det="$(grep '^RESULT' "$log" | tail -1)cells=$(basename "$CELLS"); lib=$(basename "$LIB")"
        if [ $rc -eq 0 ]; then st=pass; ok=true; else st=failed; ok=false; fi ;;
    esac
    local t1; t1=$(now)
    record "$id" "$kind" "$st" "$ok" "$(perl -e "printf '%.3f', $t1 - $t0")" "logs/$id.log" "$det"
}

if [ "${1:-}" = __job ]; then shift; job "$@"; exit 0; fi

# ------------------------------------------------------------------ driver
GOLDEN="$(cd "$VERIF/../snapshot" && pwd)/divider.v"
RTL=""; OUT=""; JOBS=3; GATE=""; GCFG=00; LEMMAS=
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
case $GCFG in 00|11) ;; *) echo "--config must be 00 or 11" >&2; exit 2 ;; esac
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
    CONFIGS=$GCFG
else
    CONFIGS="00 11"
fi
if [ -n "$LEMMAS" ]; then
    [ -f "$LEMMAS" ] || { echo "lemma file not found: $LEMMAS" >&2; exit 2; }
    LEMMAS="$(cd "$(dirname "$LEMMAS")" && pwd)/$(basename "$LEMMAS")"
elif [ -z "$GATE" ] && [ "$(shasum -a 256 < "$RTL")" = "$(shasum -a 256 < "$GOLDEN")" ]; then
    LEMMAS="$VERIF/formal/golden_self_lemmas.sv"   # golden vs golden self-check
else
    LEMMAS=none
fi
export OUT GATE GCFG CELLS LIB DUT="$RTL" GOLDEN FORBID WBNAMES WB11NAMES LEMMAS

export LOGS="$OUT/logs"
rm -rf "$LOGS" "$OUT/formal/runs" "$OUT/results.json" "$OUT/run_all.console.log"
mkdir -p "$LOGS/items"
export BUILD="$(mktemp -d "${TMPDIR:-/tmp}/divider_verif.XXXXXX")"
# RTL: one file serves simulation and Yosys. Gate: both views are rebuilt by cells_prep.
cp "$RTL" "$BUILD/divider.v"
cp "$RTL" "$BUILD/divider_fv.v"
cp "$VERIF/formal/divider.sby" "$VERIF/formal/divider_props.sv" "$VERIF/formal/ref_divider_seq.v" \
   "$VERIF/formal/divider_miter.sv" "$VERIF/formal/seq_eq.sby" "$BUILD/"
if [ -n "$GATE" ]; then echo '`define GATE' > "$BUILD/fv_mode.vh"; else echo '// RTL mode' > "$BUILD/fv_mode.vh"; fi
T_START=$(now)
echo "DUT: $RTL${GATE:+ (gate-level netlist, config $GCFG, cells $CELLS, flop models from $LIB)}"
echo "seq_eq lemmas: $LEMMAS"
echo "output: $OUT"
echo "build dir: $BUILD"

phase() { # name, then job lines "id kind args..." on stdin
    echo "== phase $1"
    tee -a "$LOGS/expected.txt" | tr '\n' '\0' | xargs -0 -P "$JOBS" -n 1 sh -c '"$0" __job $1' "$SELF"
}

FV_TASKS=$(sed -n '/^\[tasks\]/,/^$/p' "$VERIF/formal/divider.sby" | awk 'NR>1 && NF {print $1}')
[ -n "$GATE" ] && echo "cells_prep prep" | phase prep
{
    echo "selftest selftest"
    echo "gen gen"
    for c in $CONFIGS; do echo "lint_$c lint $c"; done
    [ "$LEMMAS" != none ] && echo "lemma_lint lemlint"
} | phase build
{
    echo "refcheck refcheck"
    for c in $CONFIGS; do echo "edge_$c edge $c"; done
} | phase sim
{
    for t in $FV_TASKS; do
        case " $CONFIGS " in *" ${t: -2} "*) ;; *) continue ;; esac
        # gate mode: the white-box result proofs need RTL register names (SPEC 6), and
        [ -n "$GATE" ] && [ "${t#result_}" != "$t" ] && continue
        # gate mode: covers are harness reachability (checked on the RTL); at gate level they
        # cost minutes (cover_00 took 423 s), so they are not rerun
        [ -n "$GATE" ] && [ "${t#cover_}" != "$t" ] && continue
        echo "fv_$t sby $t"
    done
    if [ -n "$GATE" ]; then echo "eqy_rtl eqy $GCFG"; else for c in $CONFIGS; do echo "eqy_rtl_$c eqy $c"; done; fi
    for c in $CONFIGS; do echo "seq_eq_$c seq $c"; echo "fv_sanity_seq_$c seq $c sanity"; done
} | phase formal

T_END=$(now)
"$PY" - "$LOGS/items" "$OUT/results.json" "$LOGS/expected.txt" "$RTL" "$T_START" "$T_END" "$GATE" "$CELLS" "$LIB" "$GCFG" "$GOLDEN" "$LEMMAS" <<'EOF' | tee "$OUT/run_all.console.log"
import csv, glob, hashlib, json, os, re, subprocess, sys
items_dir, out, exp_file, rtl, t0, t1, gate, cells, lib, gcfg, golden, lemmas = sys.argv[1:13]
# Standard (AGENT_CONTEXT) label per item, next to the contract's own status.
LABEL = {"proven": "proven", "pass-edge-spot": "pass-sampled", "not-proven": "inconclusive",
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
    # Only a white-box result proof that is unsupported on a non-golden DUT is non-gating.
    i["gating"] = not (i["status"] == "unsupported" and i["id"].startswith("fv_result_"))
    i["expected_outcome"] = "fail" if i["id"].startswith("fv_sanity") else "pass"
    if i["status"] == "covered":
        m = re.search(r"depth=(\d+)", i["detail"])
        i["depth"] = int(m.group(1)) if m else None
seen = {i["id"] for i in items}
for line in open(exp_file):
    f = line.split()
    if f and f[0] not in seen:
        items.append({"id": f[0], "kind": f[1], "status": "inconclusive", "label": "inconclusive",
                      "expected_outcome": "pass", "ok": False, "seconds": 0.0, "gating": True,
                      "log": f"logs/{f[0]}.log", "detail": "no result recorded (job crashed)"})
# Amendment A-1: equivalence with the golden = eqy_rtl OR seq_eq (a derived gating item per
# configuration; inconclusive or not-proven counts as a fail). The constituents do not gate.
byid = {i["id"]: i for i in items}
for c in ([gcfg] if gate else ["00", "11"]):
    e = byid.get("eqy_rtl" if gate else f"eqy_rtl_{c}")
    q = byid.get(f"seq_eq_{c}")
    for x in (e, q):
        if x:
            x["gating"] = False
            x["part_of"] = f"equiv_{c}"
    okk = bool((e and e["ok"]) or (q and q["ok"]))
    items.append({"id": f"equiv_{c}", "kind": "derived", "status": "proven" if okk else "failed",
                  "label": "proven" if okk else "failed", "expected_outcome": "pass", "ok": okk,
                  "gating": True, "seconds": 0.0, "log": "",
                  "detail": f"eqy_rtl: {e['status'] if e else 'missing'}; seq_eq_{c}: {q['status'] if q else 'missing'} (ok if either is proven)"})
order = {"prep": -1, "selftest": 0, "gen": 0, "lint": 1, "lemlint": 1, "refcheck": 2, "edge": 3, "sby": 6, "eqy": 7, "seq": 8, "derived": 9}
items.sort(key=lambda i: (order.get(i["kind"], 9), i["id"]))
res = {
    "module": "divider",
    "dut": rtl,
    "dut_sha256": sha(rtl),
    "dut_is_golden": (not gate) and sha(rtl) == sha(golden),
    "mode": "gate-level" if gate else "rtl",
    "configs": [gcfg] if gate else ["00", "11"],
    "config_meaning": "first digit LATCH_DENOMINATOR, second CHECK_INVALID; 00 shipped, 11 defaults",
    "seq_eq_lemmas": None if lemmas == "none" else lemmas,
    "seq_eq_lemmas_sha256": None if lemmas == "none" else sha(lemmas),
    "cells": cells if gate else None,
    "flop_liberty": lib if gate else None,
    "tools": {"iverilog": ver("iverilog -V 2>&1"), "verilator": ver("verilator --version"),
              "yosys": ver("yosys -V"), "z3": ver("z3 --version")},
    "total_seconds": round(float(t1) - float(t0), 3),
    "items_total": len(items),
    "items_ok": sum(i["ok"] for i in items),
    "gating_total": sum(i["gating"] for i in items),
    "gating_ok": sum(i["ok"] for i in items if i["gating"]),
    "all_ok": bool(items) and all(i["ok"] for i in items if i["gating"]),
    "items": items,
}
json.dump(res, open(out, "w"), indent=2)
for i in items:
    print(f'{i["id"]:<20} {i["status"]:<19} {i["label"]:<13} {"" if i["gating"] else "(non-gating) "}{i["seconds"]:8.2f}s  {i["detail"][:120]}')
print(f'TOTAL {res["gating_ok"]}/{res["gating_total"]} gating ok, all_ok={res["all_ok"]}; {res["total_seconds"]} s')
sys.exit(0 if res["all_ok"] else 1)
EOF
rc=${PIPESTATUS[0]}
rm -rf "$BUILD"
exit $rc
