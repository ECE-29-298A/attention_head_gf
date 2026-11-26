#!/bin/bash
# Agent 2: independent reference for exp_lut, checked FORMALLY against a design (D9/D9b: no
# exhaustive simulation).
# Usage: run_ref.sh [rtl.v] [outdir]     (default: review/golden_copy/exp_lut.v, review/ref/out)
#   (1) ref_exact.py: rational-interval-certified table, exact thresholds, generated
#       ref_threshold.v (comparator chain) and ref_exp_lut.v (full reference module)
#   (2) EQY, design vs ref_exp_lut.v, REGISTERED = 0 (combinational: complete) and
#       REGISTERED = 1 (state g_registered.W_r/done_r matched by name: unbounded, depth-1 induction)
#   (3) Yosys SAT miter, design (REGISTERED = 0) W and done vs ref_threshold, all inputs
#   (4) python/src/attention_model.py EXP_TABLE equal to the certified table, exp_weight() agrees
#       at the thresholds +-1 and 3,000 random points per shift (sampled; checks the spec model,
#       not the design)
# Exit 0 only if all pass. The earlier exhaustive Verilator sweep (exhaustive_sweep.cpp) is no
# longer run (D9); its pre-D9 outputs are in review/superseded_pre_D9/.
set -u
export PATH="/opt/homebrew/bin:$PATH"
HERE="$(cd "$(dirname "$0")" && pwd)"
RTL="$(cd "$(dirname "${1:-$HERE/../golden_copy/exp_lut.v}")" && pwd)/$(basename "${1:-exp_lut.v}")"
OUT="${2:-$HERE/out}"; mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"
ROOT="$(cd "$HERE/../../../../.." && pwd)"
T="$(mktemp -d "${TMPDIR:-/tmp}/el_ref.XXXXXX")"
/usr/local/bin/python3 "$HERE/ref_exact.py" > "$OUT/ref_exact.log" || { echo "ref_exact FAIL"; exit 1; }
rc=0
for R in 0 1; do
  mkdir -p "$T/eq$R"; cp "$RTL" "$T/eq$R/gold.v"; cp "$HERE/ref_exp_lut.v" "$T/eq$R/gate.v"
  cat > "$T/eq$R/eq.eqy" <<EOF
[gold]
read_verilog -sv gold.v
chparam -set REGISTERED $R exp_lut
prep -top exp_lut
memory_map; opt_clean

[gate]
read_verilog -sv gate.v
chparam -set REGISTERED $R exp_lut
prep -top exp_lut
memory_map; opt_clean

[strategy sat]
use sat
depth 1
EOF
  ( cd "$T/eq$R" && timeout 600 /usr/local/bin/python3 "$HOME/.local/bin/eqy" -f eq.eqy > eqy.log 2>&1 ); r=$?
  cp "$T/eq$R/eqy.log" "$OUT/eqy_ref_R$R.log"
  res=$(grep -o "DONE ([A-Z]*" "$OUT/eqy_ref_R$R.log" | tail -1 | sed 's/DONE (//')
  echo "eqy design vs ref_exp_lut REGISTERED=$R: rc=$r result=${res:-none} ($(grep -c 'Successfully proved' "$OUT/eqy_ref_R$R.log") partitions proved)"
  [ "$res" = PASS ] || rc=1
done
cp "$RTL" "$T/exp_lut.v"; cp "$HERE/ref_threshold.v" "$T/"
# top-level miter: W(rtl, REGISTERED=0) == W(ref_threshold) and done == start, all inputs
cat > "$T/wrap.v" <<'EOF'
module cmp(input wire [21:0] D, input wire [3:0] shift, input wire start, output wire ok);
  wire done; wire [7:0] Wg, Wr;
  exp_lut #(.REGISTERED(0)) u(.clk(1'b0), .rst_n(1'b1), .start(start), .D(D), .shift(shift), .done(done), .W(Wg));
  ref_threshold r(.D(D), .shift(shift), .W(Wr));
  assign ok = (Wg == Wr) && (done == start);
endmodule
EOF
( cd "$T" && yosys -q -l sat.log -p "read_verilog exp_lut.v ref_threshold.v wrap.v; hierarchy -check -top cmp; proc; flatten; memory; opt; sat -verify -prove ok 1 -show-inputs cmp" ) > /dev/null 2>&1; r=$?
cp "$T/sat.log" "$OUT/sat_proof.log"
echo "sat proof W(rtl)==W(ref_threshold), done==start, all inputs: rc=$r ($(grep -c 'no model found: SUCCESS' "$OUT/sat_proof.log") SAT SUCCESS)"; [ $r -eq 0 ] || rc=1
/usr/local/bin/python3 - "$ROOT" "$HERE" > "$OUT/pymodel.log" 2>&1 <<'EOF'
import json, random, sys
sys.path.insert(0, sys.argv[1] + "/python/src")
import attention_model as am
ref = json.load(open(sys.argv[2] + "/table.json"))
W, TH = ref["W"], {int(k): v for k, v in ref["thresholds"].items()}
assert am.EXP_TABLE == W[:ref["first_zero_index"]], (am.EXP_TABLE, W)
rng = random.Random(7); n = 0
for s in range(16):
    pts = set(range(0, 64)) | {t + d for t in TH[s] for d in (-1, 0, 1)} | {rng.randrange(0, 2088961) for _ in range(3000)}
    for D in pts:
        if 0 <= D <= 2088960:
            e = W[sum(D >= t for t in TH[s])]
            got = am.exp_weight(D, 0, score_shift=s)
            assert got == e, (D, s, got, e); n += 1
print("python model agrees with exact reference at", n, "points; EXP_TABLE equal")
EOF
r=$?; echo "python model: rc=$r $(tail -1 "$OUT/pymodel.log")"; [ $r -eq 0 ] || rc=1
rm -rf "$T"
exit $rc
