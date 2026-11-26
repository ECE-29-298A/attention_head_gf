// seq_eq lemmas for mutant m18 (invalid_r no longer flags denominator == 0). At 11 the ports
// still equal the golden's: with saved_divisor == 0 every quotient bit is 1, so the
// candidate's overflow check returns 0 exactly where the golden's invalid flag does.
l_state: assert property (cand.state == gold.state);
l_step:  assert property (gold.state == 2'd0 || cand.step == gold.step);
l_quot:  assert property (gold.state == 2'd0 || cand.quotient == gold.quotient);
l_rem:   assert property (gold.state == 2'd0 || cand.remainder_value == gold.remainder_value);
l_neg:   assert property (gold.state == 2'd0 || cand.negative == gold.negative);
// @config 11
l_div:   assert property (gold.state == 2'd0 || cand.g_divisor.saved_divisor == gold.g_divisor.saved_divisor);
l_inv:   assert property (gold.state == 2'd0 || cand.invalid_r == gold.invalid_r || gold.g_divisor.saved_divisor == 12'd0);
l_q0d:   assert property (gold.state != 2'd1 || gold.g_divisor.saved_divisor != 12'd0 || (gold.quotient | (23'h7fffff << gold.step)) == 23'h7fffff);
l_q0r:   assert property (gold.state != 2'd2 || gold.g_divisor.saved_divisor != 12'd0 || gold.quotient == 23'h7fffff);
