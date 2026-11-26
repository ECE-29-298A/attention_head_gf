// seq_eq lemmas for the GF180 golden netlists against the golden RTL. As formal/golden_self_lemmas.sv,
// except that at 11 the mapped netlist names the divisor and invalid flops after their aliases.
// control and output registers equal from cycle 1; datapath registers equal while busy
// (IDLE reloads them from the shared inputs at every edge).
l_state: assert property (cand.state == gold.state);
l_step:  assert property (gold.state == 2'd0 || cand.step == gold.step);
l_quot:  assert property (gold.state == 2'd0 || cand.quotient == gold.quotient);
l_rem:   assert property (gold.state == 2'd0 || cand.remainder_value == gold.remainder_value);
l_neg:   assert property (gold.state == 2'd0 || cand.negative == gold.negative);
// @config 11
l_div:   assert property (gold.state == 2'd0 || cand.divisor == gold.g_divisor.saved_divisor);
l_inv:   assert property (gold.state == 2'd0 || cand.invalid == gold.invalid_r);
