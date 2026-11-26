#!/usr/bin/env python3
"""Agent 2: RTL mutants of divider (golden = review/golden_copy/divider.v, a copy of snapshot/divider.v).
Each mutant is one checked text edit (every old string must match exactly once, unless 'ALL').
Writes mutants/<name>.v (first line "// mutant <name>: <description>") and mutants/MANIFEST.json.
Classes: functional-bug (wrong in the chip configuration LATCH=0/CHECK=0),
         out-of-context-bug (wrong only at the default 1/1 or another non-chip configuration, or in a
                             protocol case the chip never exercises),
         equivalent (expected survivor; EQY to confirm)."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
G = open(os.path.join(HERE, "golden_copy", "divider.v")).read()
M = []
def m(name, cls, scope, desc, *pairs): M.append((name, cls, scope, desc, pairs))

m("m01_latency_plus1", "functional-bug", "all", "DIVIDE ends at step 23 (24 divide steps, done one cycle late)",
  ("DIVIDE: if (step == 5'd22)", "DIVIDE: if (step == 5'd23)"))
m("m02_latency_minus1", "functional-bug", "all", "DIVIDE ends at step 21 (22 divide steps, done one cycle early, wrong value)",
  ("DIVIDE: if (step == 5'd22)", "DIVIDE: if (step == 5'd21)"))
m("m03_ties_toward_zero", "functional-bug", "all", "exact ties (2R == L) round toward zero for both signs",
  ("wire subtract = !difference[13];", "wire subtract = !difference[13] && !(state == ROUND && difference[12:0] == 13'd0);"))
m("m04_neg_ties_up", "functional-bug", "all", "negative exact ties round toward +inf (half up in signed terms)",
  ("wire subtract = !difference[13];", "wire subtract = !difference[13] && !(state == ROUND && negative && difference[12:0] == 13'd0);"))
m("m05_neg_off_by_one", "functional-bug", "all", "negative results use ~q + s instead of ~q + !s (off by -1)",
  ("{11'b0, subtract ^ negative}", "{11'b0, subtract}"))
m("m06_sign_from_bit18", "functional-bug", "all", "sign latched from sum_in[18] instead of sum_in[19]",
  ("negative <= sum_in[19];", "negative <= sum_in[18];"))
m("m07_start_restarts", "out-of-context-bug", "all", "a start while busy restarts the datapath (busy-ignore dropped for the datapath)",
  ("quotient <= state == IDLE ?", "quotient <= (state == IDLE || start) ?"),
  ("remainder_value <= state == IDLE ?", "remainder_value <= (state == IDLE || start) ?"),
  ("step <= state == IDLE ?", "step <= (state == IDLE || start) ?"))
m("m08_shift_beats_done", "out-of-context-bug", "all", "a shift in the completion cycle overrides the new result",
  ("            if (shift) result <= {result[10:0], 1'b0};\n            case (state)",
   "            case (state)"),
  ("                default: state <= IDLE;\n            endcase\n",
   "                default: state <= IDLE;\n            endcase\n            if (shift) result <= {result[10:0], 1'b0};\n"))
m("m09_shift_rotates", "functional-bug", "all", "shift rotates result[11] into bit 0 instead of zero fill",
  ("if (shift) result <= {result[10:0], 1'b0};", "if (shift) result <= {result[10:0], result[11]};"))
m("m10_reset_keeps_result", "functional-bug", "all", "synchronous reset does not clear result",
  ("            done <= 1'b0;\n            result <= 12'sd0;\n        end else begin", "            done <= 1'b0;\n        end else begin"))
m("m11_reset_keeps_done", "functional-bug", "all", "synchronous reset does not clear done (done holds through reset)",
  ("            state <= IDLE;\n            done <= 1'b0;\n            result <= 12'sd0;", "            state <= IDLE;\n            result <= 12'sd0;"))
m("m12_reset_no_abort", "functional-bug", "all", "reset does not abort a running division (state only reset when idle)",
  ("        if (!rst_n) begin\n            state <= IDLE;", "        if (!rst_n) begin\n            if (state == IDLE) state <= IDLE;"))
m("m13_latch_always", "out-of-context-bug", "L1", "LATCH_DENOMINATOR=1 samples the denominator every cycle (behaves like 0)",
  ("            if (state == IDLE) saved_divisor <= denominator;", "            saved_divisor <= denominator;"))
m("m14_remainder_not_cleared", "functional-bug", "all", "remainder is not cleared at load (holds its old value through IDLE)",
  ("remainder_value <= state == IDLE ? 12'd0 : next_remainder;", "remainder_value <= state == IDLE ? remainder_value : next_remainder;"))
m("m15_ovf_neg_2048", "out-of-context-bug", "C1", "CHECK_INVALID=1 flags the valid result -2048 as overflow (rare value)",
  ("negative ? rounded > 13'd2048 : rounded > 13'd2047", "negative ? rounded > 13'd2047 : rounded > 13'd2047"))
m("m16_rare_point", "functional-bug", "all", "rare value: result corrupted only for sum_in = 12345 with denominator = 678 (accept-time point)",
  ("    reg negative, invalid_r;", "    reg negative, invalid_r, rare_r;"),
  ("            negative <= sum_in[19];", "            negative <= sum_in[19];\n            rare_r <= sum_in == 20'sd12345 && denominator == 12'd678;"),
  ("                    else result <= signed_result;", "                    else result <= signed_result ^ {11'b0, rare_r};"))
m("m17_rare_maxL", "functional-bug", "all", "rare value: rounding increment lost when the divisor is 4095",
  ("wire [11:0] signed_result = (quotient[11:0] ^ {12{negative}}) + {11'b0, subtract ^ negative};",
   "wire [11:0] signed_result = (quotient[11:0] ^ {12{negative}}) + {11'b0, (subtract && divisor != 12'hFFF) ^ negative};"))
m("m18_invalid_den0_dropped", "out-of-context-bug", "C1", "CHECK_INVALID=1 no longer flags denominator == 0",
  ("invalid_r <= denominator == 12'd0 || sum_in == 20'sh80000;", "invalid_r <= sum_in == 20'sh80000;"))
m("m19_busy_low_in_round", "out-of-context-bug", "all", "busy is low in the ROUND cycle (busy = state == DIVIDE)",
  ("assign busy = state != IDLE;", "assign busy = state == DIVIDE;"))
m("m20_done_sticky", "functional-bug", "all", "done is not cleared after its pulse (stays high until reset)",
  ("            done <= 1'b0;\n            if (shift)", "            if (shift)"))
m("m21_default_check0", "out-of-context-bug", "default", "default CHECK_INVALID changed from 1 to 0",
  ("parameter CHECK_INVALID = 1)", "parameter CHECK_INVALID = 0)"))
m("m22_default_latch0", "out-of-context-bug", "default", "default LATCH_DENOMINATOR changed from 1 to 0",
  ("parameter LATCH_DENOMINATOR = 1,", "parameter LATCH_DENOMINATOR = 0,"))
m("m23_carry_bit8_lost", "functional-bug", "all", "the round/sign incrementer drops the carry out of bit 7",
  ("wire [11:0] signed_result = (quotient[11:0] ^ {12{negative}}) + {11'b0, subtract ^ negative};",
   "wire [11:0] sr_x = quotient[11:0] ^ {12{negative}};\n    wire [8:0] sr_lo = {1'b0, sr_x[7:0]} + {8'b0, subtract ^ negative};\n    wire [11:0] signed_result = {sr_x[11:8], sr_lo[7:0]};"))
m("m24_start_during_reset", "functional-bug", "all", "a start in a reset cycle is accepted (reset no longer beats start)",
  ("        if (!rst_n) begin\n            state <= IDLE;", "        if (!rst_n) begin\n            state <= (state == IDLE && start) ? DIVIDE : IDLE;"))
# equivalent rewrites (expected survivors)
m("e01_latch_on_start", "equivalent", "all", "saved_divisor loaded only at accept (state == IDLE && start)",
  ("            if (state == IDLE) saved_divisor <= denominator;", "            if (state == IDLE && start) saved_divisor <= denominator;"))
m("e02_negate_form", "equivalent", "all", "signed_result written as negative ? -(q + s) : q + s",
  ("wire [11:0] signed_result = (quotient[11:0] ^ {12{negative}}) + {11'b0, subtract ^ negative};",
   "wire [11:0] signed_result = negative ? 12'd0 - rounded[11:0] : rounded[11:0];"))
m("e03_compare_form", "equivalent", "all", "subtract computed by >= and the remainder by a separate subtraction",
  ("wire subtract = !difference[13];\n    wire [11:0] next_remainder = subtract ? difference[11:0] : trial[11:0];",
   "wire subtract = trial >= {1'b0, divisor};\n    wire [12:0] trial_minus = trial - {1'b0, divisor};\n    wire [11:0] next_remainder = subtract ? trial_minus[11:0] : trial[11:0];"))
m("e04_magnitude_neg", "equivalent", "all", "magnitude written as a two's complement negate of the full sum",
  ("wire [18:0] magnitude = sum_in[19] ? (~sum_in[18:0] + 19'd1) : sum_in[18:0];",
   "wire [19:0] neg_sum = -sum_in;\n    wire [18:0] magnitude = sum_in[19] ? neg_sum[18:0] : sum_in[18:0];"))
m("e05_step_hold_in_idle", "equivalent", "all", "step cleared only on the accept edge (holds while idle without start)",
  ("step <= state == IDLE ? 5'd0 : step + 5'd1;", "step <= state == IDLE ? (start ? 5'd0 : step) : step + 5'd1;"))
m("e06_done_explicit", "equivalent", "all", "done written as a single assignment from the ROUND state",
  ("            done <= 1'b0;\n            if (shift)", "            done <= state == ROUND;\n            if (shift)"),
  ("                    done <= 1'b1;\n", ""))

def main():
    os.makedirs(os.path.join(HERE, "mutants"), exist_ok=True)
    man = {}
    for name, cls, scope, desc, pairs in M:
        t = G
        for old, new in pairs:
            assert t.count(old) == 1, f"{name}: {t.count(old)} matches for {old[:60]!r}"
            t = t.replace(old, new)
        assert t != G
        open(os.path.join(HERE, "mutants", name + ".v"), "w").write(f"// mutant {name}: {desc}\n" + t)
        man[name] = {"class": cls, "scope": scope, "description": desc}
    json.dump(man, open(os.path.join(HERE, "mutants", "MANIFEST.json"), "w"), indent=1)
    print(len(man), "mutants")

if __name__ == "__main__":
    main()
