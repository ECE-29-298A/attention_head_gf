#!/bin/bash
# ripple_add verification contract: reruns every item and writes results.json.
#
# Usage: run_all.sh [--rtl FILE --out DIR] [--gate N [--cells DIR]] [--jobs J]
#   --rtl FILE  design under test (default: golden pd_flow/baseline/original_rtl/ripple_add.v).
#               Later phases pass their implementation here; the contract is unchanged.
#   --out DIR   where results.json, run_all.console.log, logs/ and formal/runs/ go.
#               Required with --rtl; may not be this verif/ directory (the Phase 1 golden
#               evidence lives here and is only written by a run on the golden RTL).
#               Default without --rtl: this directory.
#   --gate N    FILE is a gate-level netlist whose top module ripple_add has no parameter
#               and width N. Only the items for that N run (SPEC.md section 6).
#   --cells DIR cell Verilog models for --gate (default: GF180 7-track,
#               $PDKV/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/verilog).
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
NCOV=16   # covers in formal/ripple_add_props.sv

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
    lint)   # N (or "default")
        local n=$1 gv="" cp="" nn=$1
        # Gate mode: fixed-width netlist, no parameter to set. The cell models are appended to
        # the DUT file (gate/extract_cells.py), so Verilator's file-naming style warning
        # DECLFILENAME is an artefact of that packaging and is disabled (SPEC.md section 6).
        if [ -n "$GATE" ]; then nn=$GATE; gv="-Wno-DECLFILENAME"
        elif [ "$n" != default ]; then gv="-GN=$n"; cp="-chparam N $n"; else nn=16; fi
        (
            echo "== verilator --lint-only -Wall $gv"
            verilator --lint-only -Wall -Wno-fatal $gv --top-module ripple_add ripple_add.v 2> "lint_$n.vlog"; r1=$?
            cat "lint_$n.vlog"; echo "verilator_rc=$r1"
            # Documented waiver (SPEC.md R8): the golden RTL computes the carry out c[N] of the
            # last full adder and drops it by design. Only that exact warning is waived.
            "$PY" "$VERIF/lint/check_lint.py" "lint_$n.vlog" "$nn" || r1=1
            echo "== yosys structural check"
            # proc -noopt: no constant folding before the checks, so a functionally redundant
            # combinational loop is still visible to check (logic loop) and scc.
            yosys -q -l "lint_$n.ylog" -p "read_verilog ripple_add.v; hierarchy -check -top ripple_add $cp; proc -noopt; flatten; check -assert; scc -all_cell_types -select; select -assert-none %; select -clear; select -assert-none t:\$ff t:\$dff* t:\$adff* t:\$sdff* t:\$aldff* t:\$dlatch* t:\$adlatch* t:\$sr t:\$mem* t:\$anyinit t:\$_FF_ t:\$_DFF* t:\$_SDFF* t:\$_ALDFF* t:\$_DLATCH* t:\$_SR_*; select -assert-none t:* t:\$* %d; write_json lint_$n.json"; r2=$?
            cat "lint_$n.ylog"; echo "yosys_rc=$r2"
            echo "== interface check"
            "$PY" "$VERIF/lint/check_interface.py" "lint_$n.json" "$nn"; r3=$?
            echo "interface_rc=$r3"
            [ $r1 -eq 0 ] && [ $r2 -eq 0 ] && [ $r3 -eq 0 ]
        ) > "$log" 2>&1; rc=$?
        det=$(grep '^RESULT' "$log" | tail -1)
        if [ $rc -ne 0 ]; then st=failed; ok=false
        elif grep -q '^RESULT lint .*waived=[1-9]' "$log"; then st=pass-with-waiver; ok=true
        else st=pass; ok=true; fi
        det="$det; $(grep '^RESULT lint' "$log" | tail -1)" ;;
    build)  # N
        local n=$1 gv="-GN=$1"
        [ -n "$GATE" ] && gv=""
        timeout $T_BUILD verilator --cc --exe --build --build-jobs 1 -O3 $gv \
            -CFLAGS "-O2 -DNPARAM=$n" --top-module ripple_add --Mdir "obj_$n" -o sim \
            ripple_add.v tb_ripple_add.cpp > "$log" 2>&1; rc=$?
        det="obj_$n/sim"
        if [ $rc -eq 0 ] && [ -x "obj_$n/sim" ]; then st=pass; ok=true
        elif [ $rc -eq 124 ]; then st=timed-out; ok=false; else st=failed; ok=false; fi ;;
    exh)    # N: exhaustive Verilator run + independent Python checksum of the same space
        local n=$1
        (
            timeout $T_SIM "obj_$n/sim" exhaustive; r1=$?
            echo "sim_rc=$r1"
            "$PY" "$VERIF/model/golden_model.py" checksum --n "$n"; r2=$?
            echo "model_rc=$r2"
            exit $(( r1 == 124 ? 124 : (r1 || r2) ))
        ) > "$log" 2>&1; rc=$?
        local cs_sim cs_mod
        cs_sim=$(sed -n 's/^RESULT.*checksum=\(0x[0-9a-f]*\).*/\1/p' "$log")
        cs_mod=$(sed -n 's/^CHECKSUM.*checksum=\(0x[0-9a-f]*\).*/\1/p' "$log")
        det="$(grep '^RESULT' "$log" | tail -1); model_checksum=$cs_mod"
        if [ $rc -eq 0 ] && [ -n "$cs_sim" ] && [ "$cs_sim" = "$cs_mod" ]; then st=pass-exhaustive; ok=true
        elif [ $rc -eq 124 ]; then st=timed-out; ok=false
        else st=failed; ok=false; det="$det; checksum_match=$([ "$cs_sim" = "$cs_mod" ] && echo yes || echo no)"; fi ;;
    rand)   # N count seed: in-TB reference
        local n=$1 cnt=$2 seed=$3
        timeout $T_SIM "obj_$n/sim" random "$cnt" "$seed" > "$log" 2>&1; rc=$?
        det=$(grep '^RESULT' "$log" | tail -1)
        if [ $rc -eq 0 ]; then st=pass-sampled; ok=true
        elif [ $rc -eq 124 ]; then st=timed-out; ok=false; else st=failed; ok=false; fi ;;
    vec)    # N random seed ivl|noivl: golden-model vectors on Verilator (and Icarus if ivl)
        local n=$1 k=$2 seed=$3 ivl=$4 written
        (
            "$PY" "$VERIF/model/golden_model.py" vectors --n "$n" --random "$k" --seed "$seed" --out "vec_$n.txt" || exit 1
            shasum -a 256 "vec_$n.txt"
            echo "== verilator"; timeout $T_SIM "obj_$n/sim" vectors "vec_$n.txt"; r1=$?
            r2=0
            if [ "$ivl" = ivl ]; then
                echo "== icarus"
                iverilog -g2012 $IVDEF -o "ivl_$n.vvp" -P tb_vectors.N=$n tb_vectors.sv ripple_add.v && \
                    timeout $T_SIM vvp -n "ivl_$n.vvp" +VEC="vec_$n.txt"; r2=$?
            fi
            exit $(( r1 == 124 || r2 == 124 ? 124 : (r1 || r2) ))
        ) > "$log" 2>&1; rc=$?
        written=$(sed -n 's/^RESULT vectors.*written=\([0-9]*\).*/\1/p' "$log")
        local v1 v2
        v1=$(sed -n 's/^RESULT mode=vectors.* vectors=\([0-9]*\) .*/\1/p' "$log")
        v2=$(sed -n 's/^RESULT sim=icarus.* vectors=\([0-9]*\) .*/\1/p' "$log")
        [ "$ivl" = ivl ] || v2=$written   # Icarus not run for this N
        det="golden_vectors=$written verilator_checked=$v1 icarus_checked=$([ "$ivl" = ivl ] && echo "$v2" || echo not-run); $(grep '^RESULT mode' "$log" | tail -1); $(grep '^RESULT sim=icarus' "$log" | tail -1)"
        if [ $rc -eq 0 ] && [ -n "$written" ] && [ "$written" = "$v1" ] && [ "$written" = "$v2" ]; then st=pass-sampled; ok=true
        elif [ $rc -eq 124 ]; then st=timed-out; ok=false; else st=failed; ok=false; fi ;;
    sby)    # task
        local t=$1 sstat
        # Each task runs from its own copy of the .sby file in its own directory, so parallel
        # SBY invocations never share SBY's status database (concurrent access to one
        # database caused sqlite "disk I/O error" crashes).
        rm -rf "fv_$t"; mkdir "fv_$t"
        cp ripple_add.v ripple_add_props.sv "fv_$t/"
        if [ -n "$GATE" ]; then
            sed 's/read_verilog -formal -sv /read_verilog -formal -sv -DGATE_LEVEL /' ripple_add.sby > "fv_$t/ripple_add.sby"
        else
            cp ripple_add.sby "fv_$t/"
        fi
        cd "fv_$t" || exit 1
        timeout $T_FV "$PY" "$HOME/.local/bin/sby" -f ripple_add.sby "$t" > "$log" 2>&1; rc=$?
        sstat=$(awk '{print $1}' "ripple_add_$t/status" 2>/dev/null)
        local nas ncov nreach
        nas=$("$PY" "$VERIF/formal/count_props.py" "ripple_add_$t/model/design.json" 2>/dev/null)
        ncov=$(sed -n 's/.*Reached cover statement in step [0-9]* at ripple_add_props: \(c_[a-z_]*\).*/\1/p' "$log" | sort -u | wc -l | tr -d ' ')
        nreach=$(grep -ci 'unreached cover' "$log")
        if [ $rc -eq 124 ]; then st=timed-out; ok=false; det="sby_status=${sstat:-none}; timeout ${T_FV}s"
        elif grep -q 'Traceback' "$log" || { [ "$sstat" != PASS ] && [ "$sstat" != FAIL ]; }; then
            # tool or infrastructure error: no verdict either way (not ok)
            st=inconclusive; ok=false
            det="tool/infrastructure error: sby_status=${sstat:-none}; $(grep -m1 'Error' "$log" | cut -c1-160)"
        else
        case $t in
        prove_*|pdr_*)
            det="sby_status=$sstat $nas; $(grep -o 'summary: successful proof[^.]*\|summary: engine_0 (abc pdr) returned PASS' "$log" | head -1)"
            if [ "$sstat" = PASS ] && [ "$nas" = "asserts=2 covers=0" ]; then st=proven; ok=true
            elif [ $rc -eq 124 ]; then st=timed-out; ok=false; else st=failed; ok=false; fi ;;
        cover_*)
            det="sby_status=$sstat $nas reached=$ncov unreached=$nreach"
            if [ "$sstat" = PASS ] && [ "$ncov" -eq $NCOV ] && [ "$nreach" -eq 0 ] && [ "$nas" = "asserts=2 covers=$NCOV" ]; then st=covered; ok=true
            elif [ $rc -eq 124 ]; then st=timed-out; ok=false; else st=failed; ok=false; fi ;;
        sanity_*)  # negative control: the wrong property must be refuted with a trace
            det="sby_status=$sstat (expected FAIL) $(grep -o 'failed assertion [^ ]*' "$log" | head -1)"
            if [ "$sstat" = FAIL ] && grep -q 'failed assertion ripple_add_props.a_wrong' "$log" \
               && ls ripple_add_$t/engine_0/trace*.vcd >/dev/null 2>&1; then st=failed-as-expected; ok=true
            elif [ $rc -eq 124 ]; then st=timed-out; ok=false
            else st=failed; ok=false; det="$det; negative control NOT refuted"; fi ;;
        esac
        fi
        mkdir -p "$OUT/formal/runs"
        rm -rf "$OUT/formal/runs/ripple_add_$t"
        cp -R "ripple_add_$t" "$OUT/formal/runs/" 2>/dev/null ;;
    prep)   # gate-level DUT file: netlist + the cell models it uses
        "$PY" "$VERIF/gate/extract_cells.py" "$DUT" "$CELLS" ripple_add.v > "$log" 2>&1; rc=$?
        det="$(grep '^RESULT' "$log" | tail -1); cells=$CELLS"
        if [ $rc -eq 0 ]; then st=pass; ok=true; else st=failed; ok=false; fi ;;
    esac
    local t1; t1=$(now)
    record "$id" "$kind" "$st" "$ok" "$(perl -e "printf '%.3f', $t1 - $t0")" "logs/$id.log" "$det"
}

if [ "${1:-}" = __job ]; then shift; job "$@"; exit 0; fi

# ------------------------------------------------------------------ driver
GOLDEN="$(cd "$VERIF/../../../baseline/original_rtl" && pwd)/ripple_add.v"
RTL=""; OUT=""; JOBS=6; GATE=""
CELLS="/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/verilog"
while [ $# -gt 0 ]; do
    case $1 in
    --rtl) RTL=$2; shift 2 ;;
    --out) OUT=$2; shift 2 ;;
    --gate) GATE=$2; shift 2 ;;
    --cells) CELLS=$2; shift 2 ;;
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
    CELLS="$(cd "$CELLS" && pwd)"
fi
export OUT GATE CELLS DUT="$RTL" NCOV
export IVDEF=""; [ -n "$GATE" ] && IVDEF="-DGATE_LEVEL"

export LOGS="$OUT/logs"
rm -rf "$LOGS" "$OUT/formal/runs" "$OUT/results.json" "$OUT/run_all.console.log"
mkdir -p "$LOGS/items"
export BUILD="$(mktemp -d "${TMPDIR:-/tmp}/ripple_add_verif.XXXXXX")"
cp "$RTL" "$BUILD/ripple_add.v"     # gate mode: replaced by the prep item (netlist + cells)
cp "$VERIF/sim/tb_ripple_add.cpp" "$VERIF/sim/tb_vectors.sv" \
   "$VERIF/formal/ripple_add.sby" "$VERIF/formal/ripple_add_props.sv" "$BUILD/"
T_START=$(now)
echo "DUT: $RTL${GATE:+ (gate-level netlist, N=$GATE, cells $CELLS)}"
echo "output: $OUT"
echo "build dir: $BUILD"

phase() { # name, then job lines "id kind args..." on stdin
    echo "== phase $1"
    tee -a "$LOGS/expected.txt" | tr '\n' '\0' | xargs -0 -P "$JOBS" -n 1 sh -c '"$0" __job $1' "$SELF"
}

ALL_FV_TASKS=$(sed -n '/^\[tasks\]/,/^$/p' "$VERIF/formal/ripple_add.sby" | awk 'NR>1 && NF {print $1}')
if [ -z "$GATE" ]; then
    SMALL_N="1 2 3 4 5 6 7 8 9 10 11 12"
    WIDE_N="16 22 32 64"
    FV_TASKS=$ALL_FV_TASKS
    {
        echo "selftest selftest"
        for n in default 1 8 12 16 22 32 64; do echo "lint_n$n lint $n"; done
        for n in $SMALL_N $WIDE_N; do echo "build_n$n build $n"; done
    } | phase build
    {
        for n in $SMALL_N; do echo "exh_n$n exh $n"; done
        for n in 12 22; do echo "vec_n$n vec $n 200000 $n ivl"; done
        for n in 16 32 64; do echo "vec_n$n vec $n 200000 $n noivl"; done
        echo "rand_n22 rand 22 50000000 0x2222"
        for n in 16 32 64; do echo "rand_n$n rand $n 10000000 0x$n$n"; done
    } | phase sim
else
    N=$GATE
    FV_TASKS=$(echo "$ALL_FV_TASKS" | grep "_n$N\$")
    echo "cells_prep prep" | phase prep
    {
        echo "selftest selftest"
        echo "lint_n$N lint $N"
        echo "build_n$N build $N"
    } | phase build
    {
        [ "$N" -le 12 ] && echo "exh_n$N exh $N"
        if [ "$N" -le 32 ]; then echo "vec_n$N vec $N 200000 $N ivl"; else echo "vec_n$N vec $N 200000 $N noivl"; fi
        if [ "$N" -eq 22 ]; then echo "rand_n$N rand $N 50000000 0x2222"; else echo "rand_n$N rand $N 10000000 0x$N$N"; fi
    } | phase sim
fi

for t in $FV_TASKS; do echo "fv_$t sby $t"; done | phase formal

T_END=$(now)
"$PY" - "$LOGS/items" "$OUT/results.json" "$LOGS/expected.txt" "$RTL" "$T_START" "$T_END" "$GATE" "$CELLS" <<'EOF' | tee "$OUT/run_all.console.log"
import csv, glob, hashlib, json, os, subprocess, sys
items_dir, out, exp_file, rtl, t0, t1, gate, cells = sys.argv[1:9]
# Standard (AGENT_CONTEXT) label per item, next to the contract's own status.
LABEL = {"proven": "proven", "pass-exhaustive": "pass-exhaustive", "pass-sampled": "pass-sampled",
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
        i["depth"] = 1
seen = {i["id"] for i in items}
for line in open(exp_file):
    f = line.split()
    if f and f[0] not in seen:
        items.append({"id": f[0], "kind": f[1], "status": "inconclusive", "label": "inconclusive",
                      "expected_outcome": "pass", "ok": False, "seconds": 0.0,
                      "log": f"logs/{f[0]}.log", "detail": "no result recorded (job crashed)"})
order = {"prep": -1, "selftest": 0, "lint": 1, "build": 2, "exh": 3, "vec": 4, "rand": 5, "sby": 6}
items.sort(key=lambda i: (order.get(i["kind"], 9), i["id"]))
res = {
    "module": "ripple_add",
    "dut": rtl,
    "dut_sha256": hashlib.sha256(open(rtl, "rb").read()).hexdigest(),
    "mode": "gate-level" if gate else "rtl",
    "gate_n": int(gate) if gate else None,
    "cells": cells if gate else None,
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
    print(f'{i["id"]:<20} {i["status"]:<18} {i["label"]:<15} {i["seconds"]:8.2f}s  {i["detail"][:100]}')
print(f'TOTAL {res["items_ok"]}/{res["items_total"]} ok, all_ok={res["all_ok"]}, {res["total_seconds"]} s')
sys.exit(0 if res["all_ok"] else 1)
EOF
rc=${PIPESTATUS[0]}
rm -rf "$BUILD"
exit $rc
