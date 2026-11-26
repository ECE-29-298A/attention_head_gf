// seq_eq lemmas for c_rename.v: the renamed (and, for the sign, complemented) registers
// against the golden's.
l_state: assert property (cand.fsm_q == gold.state);
l_step:  assert property (gold.state == 2'd0 || cand.count_q == gold.step);
l_quot:  assert property (gold.state == 2'd0 || cand.dividend_q == gold.quotient);
l_rem:   assert property (gold.state == 2'd0 || cand.rem_q == gold.remainder_value);
l_neg:   assert property (gold.state == 2'd0 || cand.positive_q == !gold.negative);
l_rare:  assert property (gold.state == 2'd0 || !cand.rare_q);
// @config 11
l_div:   assert property (gold.state == 2'd0 || cand.g_divisor.div_q == gold.g_divisor.saved_divisor);
l_inv:   assert property (gold.state == 2'd0 || cand.bad_q == gold.invalid_r);
