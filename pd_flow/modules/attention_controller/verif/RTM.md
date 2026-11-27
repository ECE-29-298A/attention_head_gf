# attention_controller: requirements traceability

Requirements are in SPEC.md section 2. Items are in `run_all.sh` / `results.json`.

## Requirement to item

| Req | Items (assertion labels in `formal/ctrl_int_props.vh` / `top_props.vh` / `ctrl_miter.sv`) |
|---|---|
| T1 | `fv_int_P`: `t_reset`<br>`fv_cov_g5`–`g9`: reset in every state<br>`e2e_P`: reset case |
| T2 | `fv_int_P`: `t_idle_hold`, `t_idle_fresh`, `t_idle_cont`, `j_restart`<br>`cov_g1` (cont), `cov_g2` (fresh) |
| T3 | `fv_int_P`: `t_restart`, `t_cmd_step`, `t_cmd_end`, `j_cmd`<br>`cov_g2` |
| T4 | `fv_int_P`: `t_score_step`, `t_score_value`, `t_p1_tok`, `j_sdone`<br>`cov_g2`, `cov_g3` |
| T5 | `fv_int_P`: `t_value_step`, `t_value_next`, `t_value_div`, `j_value`<br>`cov_g1`, `cov_g4` |
| T6 | `fv_int_P`: `t_ds_wait`, `t_ds_go`<br>`cov_g1` (phase wait) |
| T7 | `fv_int_P`: `t_dw_wait`, `t_dw_done`, `r_dw` |
| T8 | `fv_int_P`: `t_out_hold`, `t_out_next`<br>`cov_g1` (out_idle, out_next) |
| T9 | `fv_int_P`: `q_phase`, `r_ph` |
| T10 | `fv_int_P`: `j_div` |
| S1 | `fv_int_P`: `s_cs`, `a_ports`<br>`cov_g2` (CS# fall), `cov_g5` (CS# rise) |
| S2 | `fv_int_P`: `s_sck`, `a_ports`<br>`fv_sanity_sck_8`<br>`e2e_P`: run length in rises |
| S3 | `fv_int_P`: `s_oe`, `a_ports`<br>`e2e_P`: contention check |
| S4 | `fv_int_P`: `s_mosi`, `a_ports`<br>`fv_sanity_mosi_8`<br>`e2e_P`: flash command/address check |
| S5 | `fv_int_P`: `s_cap`<br>`fv_sanity_cap_8` |
| S6 | `fv_int_P`: `a_ports` plus `r_map`, `r_cnt`, `r_tokp`, `r_rend`, `r_ph`, `r_oi`, `r_dw` |
| C1 | `fv_int_P`: `t_load`<br>`equiv_P` (control wiring) |
| C2 | `fv_int_P`: `t_p1_tok` |
| C3 | `fv_int_P`: `q_phase`, `t_score_value`, `j_value`<br>`e2e_P` |
| C4 | `fv_int_P`: `q_weight` |
| C5 | `fv_int_P`: `t_ds_go`, `o_shift` |
| O1 | `fv_int_P`: `s_out`, `a_ports` |
| O2 | `fv_int_P`: `o_shift`<br>`cov_g1` (out_shift) |
| O3 | `e2e_P` (values against chip_attention)<br>`equiv_P` |
| P1–P2 | `seq_eq_P` (reset-anchored, freshness observers)<br>`fv_int_P` (all invariants from an arbitrary pre-reset state) |
| P3 | `lint_P` (I3 flop bound)<br>`seq_eq_P` |
| P4 | SPEC host rule H1 (not checked; documented) |
| P5 | `e2e_P` (mid-run reset)<br>`cov_g5`–`g9`<br>`fv_int_P`: `t_reset` |
| E1–E3 | `fv_top_8`: `tp_pins`, `tp_reset`, `tp_held`, `tp_noshift`<br>`fv_sanity_top_8` |
| I1–I4 | `lint_P` |
| Q1 | `equiv_P` = `eqy_rtl_P` OR `seq_eq_P`<br>`fv_sanity_seq_P` |
| A1 | `fv_int_P`: `a1_stable`, `j_div` (proven, unconditional) |
| A2 | `fv_int_P`: `a2a_sum`, `l_mirror`, `l_p2`, `l_after`, `v_*`, plus E3 (held inputs) and tape assumption T1 |
| A3 | Composition: `q_phase`, `t_value_step`, `j_value`, `t_score_value`, plus the mac contract and the 16-token bound |
| A4 | Composition: `q_weight`, A2, the weighted-average bound, plus E3 and T1 |

## Run record (golden, `--jobs 3`, this machine)

| Run | Result | Wall time |
|---|---|---|
| Clean run A | 49/49 gating ok | 47.6 s |
| Clean run B | 49/49 gating ok, statuses identical to run A | 37.1 s |
| Gate, golden netlist P = 8 (`gate/evidence/golden_8_gf180`) | 7/7 gating ok | 15.8 s |
| Each smoke mutant | killed | about 4 s |

Per-item maxima:

| Item | Time |
|---|---|
| `fv_int` | 2.2 s |
| one cover group | 4.5 s or less |
| `seq_eq` | 3.7 s |
| `eqy_rtl` | 1.7 s |
| `e2e` | 0.6 s |
