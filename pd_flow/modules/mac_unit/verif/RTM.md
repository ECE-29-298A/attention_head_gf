# mac_unit: requirements traceability (SPEC.md)

| R | Requirement | Formal (gating) | Sim / static (gating) | Covers / negative controls |
|---|---|---|---|---|
| R1 | Score accumulate | `fv_spec_P` a_S | `edge_P` score_row, score_step; `refcheck`; `selftest` | c_sc_b0_neg, c_sc_wrap, c_sc_hold |
| R2 | Bit-7 sign handling (w(7) = −128), pass 1 / pass 2 | `fv_spec_P` a_S | `selftest` dot products (64-dim ±128); `edge_P` score_step b = 7 | c_sc_b7_add, c_sc_b7_sub; `fv_sanity_sign_8` |
| R3 | Load forms and priority | `fv_spec_P` a_S | `edge_P` score_row (M extremes), mode_mix | c_load0, c_loadM_min, c_load_prio |
| R4 | score_en in accumulate mode | `fv_spec_P` a_S | `edge_P` mode_mix, random; `selftest` | c_sc_in_acc |
| R5 | Accumulate term W·v[b]·w(b) | `fv_spec_P` a_O0 | `edge_P` acc_step, v_extreme; `selftest` V sums | c_acc_add, c_acc_neg; `fv_sanity_sign_8` |
| R6 | First-token load at bit 7 | `fv_spec_P` a_O0, a_S | `edge_P` flush, v_extreme, acc_step (first × bit_sel) | c_acc_load (−255·128 at the head) |
| R7 | Ring rotation, O0(t+P) = tail(t) | `fv_spec_P` a_O0 | `edge_P` (all classes), readout | `fv_sanity_delay_8` |
| R8 | Accumulate-mode tail; hold with accum_en = 0 | `fv_spec_P` a_O0 | `edge_P` acc_hold, readout | c_acc_add |
| R9 | Score-mode bypass (ring holds) | `fv_spec_P` a_O0 | `edge_P` v_extreme (score rows between tokens) | c_hold_score |
| R10 | L update condition | `fv_spec_P` a_L | `edge_P` L, L_wrap; `selftest` L sums | c_L_first, c_L_add, c_L_wrap, c_L_sel_hold, c_L_bit_hold; `fv_sanity_lsel_8` |
| R11 | S hold | `fv_spec_P` a_S | `edge_P` | c_sc_hold |
| R12 | O0 alias, Moore outputs | `fv_spec_P` (all three) | `lint_P` structure | — |
| R13 | Interface, OUTPUTS 2/4/8, default 8 | — | `lint_P` (check_interface; default parameter at P = 8) | — |
| R14 | Power-up and structure: no reset, no init, plain posedge flops | `fv_spec_P` from any start state; `mac.sby` / `seq_eq.sby` guards | `lint_P` (no init, no reset or set flops, clk only) | smoke mutant m4 (init on S) killed |
| R15 | Lint | — | `lint_P` | — |
| R16 | Equivalence with the golden | `equiv_P` = `eqy_rtl_P` OR `seq_eq_P` | — | `fv_sanity_seq_P` |

Configurations: RTL mode runs every row at P = 8, 4 and 2; the sanity items run at P = 8 only. Gate
mode runs one P (`--config`).
