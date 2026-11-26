// seq_eq strengthening lemmas for c06 (opt/best/divider.v) against the golden (contract amendment A-1).
// Taken from the observer invariants of opt/bridge/make_bridge.py (proven there: Yosys SAT
// k-induction depth 2 plus an SBY base case from reset, both configurations).
// All are assertions, checked from cycle 1 on. Implications are written as !a || b.
// Golden IDLE is state == 2'd0; DIVIDE is 2'd1; ROUND is 2'd2. c06: step 0..22 divide, 23 round, 24 idle.
// Only candidate nets that also exist in the synthesized gate netlist are referenced (step, dq,
// remainder_value, negative, done, result, divisor, invalid, g_high_quotient.seen), so the same file
// serves the RTL and the gate modes. c06 idle (step[4] & step[3]) is written as step >= 24, which is
// the same set under l_cand_legal.

// 1. Golden state is legal. Idle; or dividing at step <= 22 with the four zero dividend LSBs (shifted
//    up by step) still zero; or rounding at step 23.
l_gold_legal: assert property (gold.state == 2'd0 || (gold.state == 2'd1 && gold.step <= 5'd22 && (gold.quotient & (23'hF << gold.step)) == 23'd0) || (gold.state == 2'd2 && gold.step == 5'd23));
// 2. c06 state is legal (reset value 24; 25..31 unreachable).
l_cand_legal: assert property (cand.step <= 5'd24);
// 3. Step correspondence: same idle phase; while busy, the same step value (23 = round on both sides).
l_idle: assert property ((gold.state == 2'd0) == (cand.step >= 5'd24));
l_step: assert property (gold.state == 2'd0 || cand.step == gold.step);
// 4. Quotient layout while busy. c06 dq = golden quotient without the 4 zero dividend bits, with the
//    quotient bits (the low step bits) complemented when negative. From step 19 on, all 19 bits are
//    quotient bits.
l_dq: assert property (gold.state == 2'd0 || cand.dq == (gold.step <= 5'd19 ? (((gold.quotient >> (gold.step + 5'd4)) << gold.step) | ((gold.quotient ^ {23{gold.negative}}) & ((23'd1 << gold.step) - 23'd1))) : {4'd0, gold.quotient[18:0] ^ {19{gold.negative}}}));
// 5. Equal datapath registers while busy.
l_rem: assert property (gold.state == 2'd0 || cand.remainder_value == gold.remainder_value);
l_neg: assert property (gold.state == 2'd0 || cand.negative == gold.negative);
// 7. Output registers equal (also implied by a_eq).
l_done: assert property (cand.done == gold.done);
l_result: assert property (cand.result == gold.result);
// @config 11
// 5 (configuration 11). Latched divisor (cand.divisor = saved_divisor) and invalid flag
// (cand.invalid = invalid_r at CHECK_INVALID=1) equal while busy.
l_div: assert property (gold.state == 2'd0 || cand.divisor == gold.g_divisor.saved_divisor);
l_inv: assert property (gold.state == 2'd0 || cand.invalid == gold.invalid_r);
// 6. High-quotient flag: the OR of golden quotient bits q0..q10 produced so far. Bit j of the
//    quotient field (the low step bits) holds q(step-1-j), so q0..q10 are bits [step-1 : step-11].
l_seen: assert property (gold.state == 2'd0 || cand.g_high_quotient.seen == (|((gold.quotient & ((23'd1 << gold.step) - 23'd1)) >> (gold.step > 5'd11 ? gold.step - 5'd11 : 5'd0))));
