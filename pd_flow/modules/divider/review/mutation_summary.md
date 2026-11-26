must-kill 33: killed 33, by formal 31, by edge 29
equivalent 11: survived 8

| Run | Class | Outcome | Gating ok | Killed by | Own ref 00 / 11 |
|---|---|---|---|---|---|
| `e01_latch_on_start` | equivalent | killed | 21/22 | eqy_rtl_11 | PASS / PASS |
| `e02_negate_form` | equivalent | survived | 22/22 | - | PASS / PASS |
| `e03_compare_form` | equivalent | survived | 22/22 | - | PASS / PASS |
| `e04_magnitude_neg` | equivalent | survived | 22/22 | - | PASS / PASS |
| `e05_step_hold_in_idle` | equivalent | killed | 20/22 | eqy_rtl_00, eqy_rtl_11 | PASS / PASS |
| `e06_done_explicit` | equivalent | survived | 22/22 | - | PASS / PASS |
| `m01_latency_plus1` | functional-bug | killed | 11/22 | edge_00, edge_11, fv_pdr_proto_00, fv_pdr_proto_11, fv_proto_00, fv_proto_11, fv_result_00, fv_result_11, fv_sanity_round_00, eqy_rtl_00, eqy_rtl_11 | UNKNOWN / UNKNOWN |
| `m02_latency_minus1` | functional-bug | killed | 7/22 | edge_00, edge_11, fv_cover_00, fv_pdr_proto_00, fv_pdr_proto_11, fv_proto_00, fv_proto_11, fv_result_00, fv_result_11, fv_sanity_lat_11, fv_sanity_round_00, fv_sanity_round_11, fv_sanity_stab_00, eqy_rtl_00, eqy_rtl_11 | UNKNOWN / UNKNOWN |
| `m03_ties_toward_zero` | functional-bug | killed | 16/22 | edge_00, edge_11, fv_result_00, fv_result_11, eqy_rtl_00, eqy_rtl_11 | UNKNOWN / UNKNOWN |
| `m04_neg_ties_up` | functional-bug | killed | 16/22 | edge_00, edge_11, fv_result_00, fv_result_11, eqy_rtl_00, eqy_rtl_11 | UNKNOWN / UNKNOWN |
| `m05_neg_off_by_one` | functional-bug | killed | 16/22 | edge_00, edge_11, fv_result_00, fv_result_11, eqy_rtl_00, eqy_rtl_11 | UNKNOWN / UNKNOWN |
| `m06_sign_from_bit18` | functional-bug | killed | 16/22 | edge_00, edge_11, fv_result_00, fv_result_11, eqy_rtl_00, eqy_rtl_11 | UNKNOWN / UNKNOWN |
| `m07_start_restarts` | out-of-context-bug | killed | 11/22 | edge_00, edge_11, fv_pdr_proto_00, fv_pdr_proto_11, fv_proto_00, fv_proto_11, fv_result_00, fv_result_11, fv_sanity_round_00, eqy_rtl_00, eqy_rtl_11 | UNKNOWN / UNKNOWN |
| `m08_shift_beats_done` | out-of-context-bug | killed | 14/22 | edge_00, edge_11, fv_cover_00, fv_cover_11, fv_result_00, fv_result_11, eqy_rtl_00, eqy_rtl_11 | UNKNOWN / UNKNOWN |
| `m09_shift_rotates` | functional-bug | killed | 12/22 | edge_00, edge_11, fv_pdr_proto_00, fv_pdr_proto_11, fv_proto_00, fv_proto_11, fv_result_00, fv_result_11, eqy_rtl_00, eqy_rtl_11 | UNKNOWN / UNKNOWN |
| `m10_reset_keeps_result` | functional-bug | killed | 8/22 | edge_00, edge_11, fv_pdr_proto_00, fv_pdr_proto_11, fv_proto_00, fv_proto_11, fv_result_00, fv_result_11, fv_sanity_lat_11, fv_sanity_round_00, fv_sanity_round_11, fv_sanity_stab_00, eqy_rtl_00, eqy_rtl_11 | FAIL / FAIL |
| `m11_reset_keeps_done` | functional-bug | killed | 9/22 | edge_00, edge_11, fv_pdr_proto_00, fv_pdr_proto_11, fv_proto_00, fv_proto_11, fv_result_00, fv_result_11, fv_sanity_round_00, fv_sanity_round_11, fv_sanity_stab_00, eqy_rtl_00, eqy_rtl_11 | FAIL / FAIL |
| `m12_reset_no_abort` | functional-bug | killed | 8/22 | edge_00, edge_11, fv_pdr_proto_00, fv_pdr_proto_11, fv_proto_00, fv_proto_11, fv_result_00, fv_result_11, fv_sanity_lat_11, fv_sanity_round_00, fv_sanity_round_11, fv_sanity_stab_00, eqy_rtl_00, eqy_rtl_11 | FAIL / FAIL |
| `m13_latch_always` | out-of-context-bug | killed | 19/22 | edge_11, fv_result_11, eqy_rtl_11 | PASS / UNKNOWN |
| `m14_remainder_not_cleared` | functional-bug | killed | 16/22 | edge_00, edge_11, fv_result_00, fv_result_11, eqy_rtl_00, eqy_rtl_11 | UNKNOWN / UNKNOWN |
| `m15_ovf_neg_2048` | out-of-context-bug | killed | 18/22 | edge_11, fv_cover_11, fv_result_11, eqy_rtl_11 | PASS / UNKNOWN |
| `m16_rare_point` | functional-bug | killed | 18/22 | fv_result_00, fv_result_11, eqy_rtl_00, eqy_rtl_11 | UNKNOWN / UNKNOWN |
| `m17_rare_maxL` | functional-bug | killed | 16/22 | edge_00, edge_11, fv_result_00, fv_result_11, eqy_rtl_00, eqy_rtl_11 | UNKNOWN / UNKNOWN |
| `m18_invalid_den0_dropped` | equivalent | killed | 20/22 | fv_result_11, eqy_rtl_11 | PASS / UNKNOWN |
| `m19_busy_low_in_round` | out-of-context-bug | killed | 9/22 | edge_00, edge_11, fv_pdr_proto_00, fv_pdr_proto_11, fv_proto_00, fv_proto_11, fv_result_00, fv_result_11, fv_sanity_round_00, fv_sanity_round_11, fv_sanity_stab_00, eqy_rtl_00, eqy_rtl_11 | UNKNOWN / UNKNOWN |
| `m20_done_sticky` | functional-bug | killed | 10/22 | edge_00, edge_11, fv_cover_00, fv_cover_11, fv_pdr_proto_00, fv_pdr_proto_11, fv_proto_00, fv_proto_11, fv_result_00, fv_result_11, eqy_rtl_00, eqy_rtl_11 | UNKNOWN / UNKNOWN |
| `m21_default_check0` | out-of-context-bug | killed | 21/22 | lint_11 | PASS / PASS |
| `m22_default_latch0` | out-of-context-bug | killed | 21/22 | lint_11 | PASS / PASS |
| `m23_carry_bit8_lost` | functional-bug | killed | 16/22 | edge_00, edge_11, fv_result_00, fv_result_11, eqy_rtl_00, eqy_rtl_11 | UNKNOWN / UNKNOWN |
| `m24_start_during_reset` | functional-bug | killed | 8/22 | edge_00, edge_11, fv_pdr_proto_00, fv_pdr_proto_11, fv_proto_00, fv_proto_11, fv_result_00, fv_result_11, fv_sanity_lat_11, fv_sanity_round_00, fv_sanity_round_11, fv_sanity_stab_00, eqy_rtl_00, eqy_rtl_11 | FAIL / FAIL |
| `gate_g01_dswap_result3_4` | functional-bug | killed | 8/12 | edge_00, fv_pdr_proto_00, fv_proto_00, eqy_rtl | - |
| `gate_g02_xor_to_xnor_407` | functional-bug | killed | 10/12 | edge_00, eqy_rtl | - |
| `gate_g03_buf_result11` | equivalent | survived | 12/12 | - | - |
| `gate_g04_clkbuf` | equivalent | survived | 12/12 | - | - |
| `gate_g05_dffnq_done` | structural | killed | 5/12 | lint_00, edge_00, fv_pdr_proto_00, fv_proto_00, fv_sanity_round_00, fv_sanity_stab_00, eqy_rtl | - |
| `gate_g06_busy_stuck0` | out-of-context-bug | killed | 6/12 | edge_00, fv_pdr_proto_00, fv_proto_00, fv_sanity_round_00, fv_sanity_stab_00, eqy_rtl | - |
| `gate_s_e02_negate_form` | equivalent | survived | 12/12 | - | - |
| `gate_s_e03_compare_form` | equivalent | survived | 12/12 | - | - |
| `gate_s_m01_latency_plus1` | functional-bug | killed | 7/12 | edge_00, fv_pdr_proto_00, fv_proto_00, fv_sanity_stab_00, eqy_rtl | - |
| `gate_s_m03_ties_toward_zero` | functional-bug | killed | 10/12 | edge_00, eqy_rtl | - |
| `gate_s_m05_neg_off_by_one` | functional-bug | killed | 10/12 | edge_00, eqy_rtl | - |
| `gate_s_m16_rare_point` | functional-bug | killed | 11/12 | eqy_rtl | - |
| `gate_s_m17_rare_maxL` | functional-bug | killed | 10/12 | edge_00, eqy_rtl | - |
| `gate_s_m23_carry_bit8_lost` | functional-bug | killed | 10/12 | edge_00, eqy_rtl | - |
