// seq_eq lemmas for the golden against itself (self-check). Strengthening invariants:
// control and output registers equal from cycle 1; datapath registers equal while busy
// (IDLE reloads them from the shared inputs at every edge).
l_state: assert property (cand.state == gold.state);
l_step:  assert property (gold.state == 2'd0 || cand.step == gold.step);
l_quot:  assert property (gold.state == 2'd0 || cand.quotient == gold.quotient);
l_rem:   assert property (gold.state == 2'd0 || cand.remainder_value == gold.remainder_value);
l_neg:   assert property (gold.state == 2'd0 || cand.negative == gold.negative);
// @config 11
l_div:   assert property (gold.state == 2'd0 || cand.g_divisor.saved_divisor == gold.g_divisor.saved_divisor);
l_inv:   assert property (gold.state == 2'd0 || cand.invalid_r == gold.invalid_r);
l_atk: assert property ((seen >>= 1) == 1'b0 || gold.state == gold.state);
