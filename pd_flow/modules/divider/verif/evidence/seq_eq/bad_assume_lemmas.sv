// must be REJECTED by the lemma lint: contains an assume
l_state: assert property (cand.state == gold.state);
a_cheat: assume property (cand.result == gold.result);
