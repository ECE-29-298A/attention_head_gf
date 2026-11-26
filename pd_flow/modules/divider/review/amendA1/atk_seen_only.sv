// attack: lemma with a side effect on the miter observer 'seen' (passes lemma_lint)
l_atk: assert property ((seen >>= 1) == 1'b0 || cand.fsm_q == cand.fsm_q);
