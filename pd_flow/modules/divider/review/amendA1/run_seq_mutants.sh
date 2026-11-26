#!/bin/bash
# Agent 2 (A-1 review): run RTL mutants through the seq_eq item only, replicating run_all.sh's
# 'seq' case step for step (same miter, same .sby, same lemma_prep gen, same status logic),
# from a contract copy V (git archive HEAD). Usage: run_seq_mutants.sh V OUTDIR mutant.v...
# Per-run timeout TMO (default 120 s; TMO_NONE, default 45 s, without lemmas): a timed-out run is never 'proven' (fails closed, as in
# run_all.sh); the induction status is recorded. For each mutant, config 00/11 and lemma mode none / golden_self_lemmas.sv. Prints one line each.
V=$1; OUT=$2; shift 2; PY=/usr/local/bin/python3; export PATH="/opt/homebrew/bin:$PATH"
GOLDEN=$(cd "$V/../snapshot" && pwd)/divider.v
mkdir -p "$OUT"
for m in "$@"; do
  b=$(basename "$m" .v)
  for c in 00 11; do
    for lm in none golden_self; do
      lf=none; tmo=${TMO_NONE:-45}; [ $lm = golden_self ] && { lf="$V/formal/golden_self_lemmas.sv"; tmo=${TMO:-120}; }
      d="$OUT/${b}_${c}_$lm"; rm -rf "$d"; mkdir -p "$d"; t=seq_$c; defs=""; [ $c = 11 ] && defs="-DP11"
      sed 's/^module divider #/module divider_gold #/' "$GOLDEN" > "$d/gold.v"
      cp "$m" "$d/divider_fv.v"; cp "$V/formal/divider_miter.sv" "$V/formal/seq_eq.sby" "$d/"; echo '// RTL mode' > "$d/fv_mode.vh"
      ( cd "$d" && echo '// no lemmas' > seq_lemmas.vh && echo '# no lemmas' > seq_lemmas.ys &&
        yosys -q -p "read_verilog -formal -sv $defs divider_miter.sv; read_verilog -formal gold.v; read_verilog -formal divider_fv.v; hierarchy -top divider_miter; proc; flatten; write_json widths.json" &&
        "$PY" "$V/formal/lemma_prep.py" gen "$lf" "$c" widths.json seq_lemmas.vh seq_lemmas.ys || exit 3
        timeout $tmo "$PY" "$HOME/.local/bin/sby" -f seq_eq.sby "$t" ) > "$d/log.txt" 2>&1; rc=$?
      nl=$(sed -n 's/^RESULT lemma_gen .*lemmas=\([0-9]*\) .*/\1/p' "$d/log.txt")
      s=$(awk '{print $1}' "$d/seq_eq_$t/status" 2>/dev/null)
      nas=$("$PY" "$V/formal/count_props.py" "$d/seq_eq_$t/model/design.json" 2>/dev/null)
      if [ $rc -eq 3 ]; then st=failed-lemma-gen
      elif [ $rc -eq 124 ]; then st="timed-out(${tmo}s; induction: $(grep -o 'Status returned by engine for induction: [A-Z]*' "$d/log.txt" | sed 's/.*: //' | head -1))"
      elif [ "$s" = PASS ] && [ "$nas" = "asserts=$((1 + ${nl:-0})) covers=0" ]; then st=proven
      elif [ "$s" = FAIL ]; then st="failed($(grep -o 'Assert failed in divider_miter: [A-Za-z_0-9]*' "$d/log.txt" | sed 's/.*: //' | sort -u | tr '\n' ' ')$(grep -o 'returned FAIL for [a-z]*' "$d/log.txt" | head -1))"
      elif [ "$s" = UNKNOWN ]; then st=not-proven
      else st="inconclusive(${s:-none})"; fi
      echo "$b $c $lm $st"
      rm -rf "$d/seq_eq_$t/model" "$d/seq_eq_$t/engine_0"/*.smt2 2>/dev/null
    done
  done
done
