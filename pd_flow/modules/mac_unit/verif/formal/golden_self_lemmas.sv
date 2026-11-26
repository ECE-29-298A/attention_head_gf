// seq_eq lemmas for the golden against itself (self-check of the lemma path; the induction
// also closes without them). Each lemma is guarded by the flush observer of its register,
// because the two instances start in independent states.
l_s: assert property (!fresh_s || cand.S == gold.S);
l_l: assert property (!fresh_l || cand.L == gold.L);
l_r0: assert property (!fresh_ring[0] || cand.ring[19:0] == gold.ring[19:0]);
l_r1: assert property (!fresh_ring[1] || cand.ring[39:20] == gold.ring[39:20]);
// @config 4 8
l_r3: assert property (!fresh_ring[3] || cand.ring[79:60] == gold.ring[79:60]);
// @config 8
l_r7: assert property (!fresh_ring[7] || cand.ring[159:140] == gold.ring[159:140]);
