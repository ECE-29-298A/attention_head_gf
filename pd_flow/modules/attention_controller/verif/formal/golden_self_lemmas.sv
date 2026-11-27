// Golden-vs-golden seq_eq lemmas (the self-check of the miter, SPEC.md section 6). Format:
// formal/lemma_prep.py. Every lemma is an ASSERTION proven together with a_eq; none is assumed.
// Control: equal from the reset anchor (reset registers) or from the first start (pos, token,
// second_pass), output_index from the first run end.
l_rst:   assert property (!an || (cand.state == gold.state && cand.flash_open == gold.flash_open
                          && cand.spi_sck == gold.spi_sck && cand.score_done == gold.score_done
                          && cand.divider_unit.state == gold.divider_unit.state
                          && cand.divider_unit.done == gold.divider_unit.done));
l_ctl0:  assert property (!an || gold.state == 3'd0 || f_ctl);
l_ctl:   assert property (!f_ctl || (cand.pos == gold.pos && cand.token == gold.token
                          && cand.second_pass == gold.second_pass));
l_oi0:   assert property (!an || gold.state < 3'd5 || f_oi);
l_oi:    assert property (!f_oi || cand.output_index == gold.output_index);
// Data path: equal where the observer says the golden register is fresh
l_nib3:  assert property (!f_nib[3] || cand.nibble[3] == gold.nibble[3]);
l_nib2:  assert property (!f_nib[2] || cand.nibble[2] == gold.nibble[2]);
l_nib1:  assert property (!f_nib[1] || cand.nibble[1] == gold.nibble[1]);
l_nib0:  assert property (!f_nib[0] || cand.nibble[0] == gold.nibble[0]);
l_q:     assert property (((cand.q ^ gold.q) & f_q) == 8'd0);
l_s:     assert property (!f_S || cand.mac.S == gold.mac.S);
l_m:     assert property (!f_M || cand.max_unit.M == gold.max_unit.M);
l_l:     assert property (!f_L || cand.mac.L == gold.mac.L);
// the divider: step from the accept edge; operands while the request is fresh; the result
l_dstep: assert property (!an || gold.divider_unit.state == 2'd0 || cand.divider_unit.step == gold.divider_unit.step);
l_dq:    assert property (!f_req || gold.divider_unit.state == 2'd0
                          || (cand.divider_unit.quotient == gold.divider_unit.quotient
                              && cand.divider_unit.remainder_value == gold.divider_unit.remainder_value
                              && cand.divider_unit.negative == gold.divider_unit.negative));
l_res:   assert property (!f_res || cand.divider_unit.result == gold.divider_unit.result);
// ring slot j is fresh where f_ring[j] (the observer rotates with the ring)
// @config all
l_r0:    assert property (!f_ring[0] || cand.mac.ring[19:0] == gold.mac.ring[19:0]);
// @config all
l_r1:    assert property (!f_ring[1] || cand.mac.ring[39:20] == gold.mac.ring[39:20]);
// @config 4 8
l_r2:    assert property (!f_ring[2] || cand.mac.ring[59:40] == gold.mac.ring[59:40]);
// @config 4 8
l_r3:    assert property (!f_ring[3] || cand.mac.ring[79:60] == gold.mac.ring[79:60]);
// @config 8
l_r4:    assert property (!f_ring[4] || cand.mac.ring[99:80] == gold.mac.ring[99:80]);
// @config 8
l_r5:    assert property (!f_ring[5] || cand.mac.ring[119:100] == gold.mac.ring[119:100]);
// @config 8
l_r6:    assert property (!f_ring[6] || cand.mac.ring[139:120] == gold.mac.ring[139:120]);
// @config 8
l_r7:    assert property (!f_ring[7] || cand.mac.ring[159:140] == gold.mac.ring[159:140]);
// @config all
