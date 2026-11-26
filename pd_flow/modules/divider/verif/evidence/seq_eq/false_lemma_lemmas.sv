// a lemma that does not hold (the quotient register is not always 0): the item must FAIL
l_state: assert property (cand.state == gold.state);
l_false: assert property (cand.quotient == 23'd0);
