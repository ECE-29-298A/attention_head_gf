# max_reg: requirements traceability matrix

Requirements are defined in `SPEC.md` §3. Item IDs are the `id` fields in `results.json`;
logs are `logs/<id>.log`, SBY work dirs (status, engine logs, cover and counterexample traces)
are `formal/runs/max_reg_<task>/`. All paths are relative to this directory.
Regenerate everything with `./run_all.sh`. A new implementation is checked with
`./run_all.sh --rtl FILE --out DIR` (RTL) or `--rtl NETLIST --gate --out DIR` (gate level);
those runs never write here. The `label` column of `results.json` gives the standard label (SPEC §5).

| Req | Requirement (short) | Evidence (results.json item IDs; assertion / cover names) | Method | Expected status |
|---|---|---|---|---|
| R1 | `M' = (en && (first \|\| S_in > M)) ? S_in : M`, any M, from power-up | `fv_prove_step`, `fv_pdr_step` (`a_step`, M unconstrained) | k-induction + abc pdr | proven |
| | | `sim_onestep` (268 M one-step checks on V×V×en×first) | reduced exhaustive | pass-sampled (pass-exhaustive-subspace) |
| | | step check from the observed M on every cycle of `vec`, `sim_ctrl`, `sim_free`, `sim_onestep`, `sim_powerup` (also before the first load, random power-up M) | simulation | pass-sampled |
| | | `selftest` (model KATs) | model self-check | pass-static |
| R2 | hold when `en = 0` (also with `first = 1` or `S_in > M`) | `fv_prove_step`, `fv_pdr_step` (`a_hold`); covers `c_en0_greater`, `c_en0_first`; `vec` (every corner pair offered with `en = 0` and with `first = 1, en = 0`); `sim_free` (`P(en)` = 0.05 regimes); `sim_ctrl` (pass 2, continue runs) | proof + cover + sim | proven |
| R3 | `first` overrides the compare | `fv_prove_step`, `fv_pdr_step` (`a_first`); covers `c_first_lower`, `c_first_equal`, `c_min_over_max_first`, `c_reload_lower`; `vec` (every corner pair as a load, back-to-back loads) | proof + cover + sim | proven |
| R4 | signed compare incl. MINNEG, MAXPOS, −1/0, sign-differing pairs | `fv_prove_step`, `fv_pdr_step` (`a_gt`, `a_le`); covers `c_gt_update`, `c_lt_hold`, `c_neg_vs_pos`, `c_pos_vs_neg`, `c_max_over_min`, `c_min_vs_max`, `c_zero_over_m1`, `c_m1_vs_zero`; `fv_sanity_unsigned` (unsigned reference refuted); `vec` (15×15 corner pairs, single-bit and ±2^k neighbours at every bit); `sim_onestep` (all sign/magnitude combinations of the top 6 bits) | proof + cover + sim | proven |
| R5 | tie: M unchanged | `fv_prove_step`, `fv_pdr_step` (`a_le` covers `S_in == M`); covers `c_tie_hold`, `c_min_tie`, `c_max_tie`; `vec` (ties at every corner); `sim_free` (tie regime), `sim_ctrl` (10 % tied scores) | proof + cover + sim | proven |
| R6 | registered output, no combinational path | `fv_prove_step`, `fv_pdr_step` (M at each step is a function of the previous step only: a combinational dependence on the free current inputs violates `a_step`); comb-path and falling-edge checks on every cycle of `vec` (Verilator and Icarus) and all `sim_*` | proof + sim | proven |
| R7 | after a load, M == max of the accepted scores; no decrease; M only takes `S_in` | `fv_prove_seq`, `fv_pdr_seq` (`a_seq`, `a_mono`, `a_src`, shadow model `mx`); covers `c_seq3_not_last`, `c_hold4`, `c_ctrl_pattern`; `vec` (list-based Python model); in-TB tracker on every cycle of all `sim_*`; `sim_ctrl` per-query `std::max` check | proof + cover + sim | proven |
| R8 | no reset, power-up value arbitrary; independent of it after a load | `fv_prove_pu`, `fv_pdr_pu` (`a_pu`, two copies with free power-up values); `fv_sanity_pu` (copies do differ before a load: power-up really free); covers `c_pu_differ`, `c_pu_converge`, `c_preload_update`; `sim_powerup` (64 distinct random power-up values, identical traces after the load); `lint` (no reset port, no reset-type flop, no `init` attribute); `.sby` guard (no `init` outside the harness, in every `fv_*` run) | proof + sim + static | proven |
| R9 | ports clk, first, en, S_in[21:0] in; M[21:0] out | `lint` (`lint/check_interface.py` on the Yosys JSON) | static | pass-static |
| R10 | lint clean | `lint` (Verilator `-Wall`, `lint/check_lint.py`; RTL: no waivers) | static | pass-static |
| R11 | 22 posedge flops on `clk` (after collapsing non-inverting buffers), no reset/latch/memory/loop/black box | `lint` (Yosys `check -assert`, `scc` empty on the unoptimised netlist, forbidden state types, `check_interface.py`: 22 flop bits, polarity, clock net after `flatten; opt_clean`); `.sby` guard in every `fv_*` run (no negedge, async, latch, memory cells; the same `flatten; opt_clean` before `prep`, so a CTS clock buffer is accepted by both and a derived clock is refused by SBY) | static | pass-static |
| R12 | controller pattern: max after pass 1, held through pass 2 and continue runs | `sim_ctrl` (115,709 queries, 202,639 per-query checks), `vec` (3,000 controller-style queries); follows from R1 to R7 (proven) | sim (+ proof of R1 to R7) | pass-sampled |
| — | checker sanity | `fv_sanity_unsigned`, `fv_sanity_pu` (must fail; traces in `formal/runs/max_reg_sanity_*/engine_0/trace.vcd`) | negative control | failed-as-expected |
| — | proofs not vacuous | every `fv_prove_*` / `fv_pdr_*` detail shows the expected assertion count (5 / 3 / 1, `formal/count_props.py`); `fv_cover`: 23/23 covers reached, 0 unreached, 9 asserts in the model, each antecedent of `a_hold`, `a_first`, `a_gt`, `a_le`, `a_seq`, `a_pu` reached by a cover; no assumptions | cover + model inspection | covered (bounded-pass, depth 10) |
| — | gate netlist equivalent to the golden RTL (gate mode) | `eqy_rtl` (EQY, sat, depth 1, state matched by name; `formal/runs/eqy_rtl/`) | equivalence proof | proven |
| — | gate-level reuse (Phase 2/3) | `gate/evidence/golden_gf180/results.json`: the GF180-mapped golden netlist (`gate/netlists/max_reg_gf180.v`) run with `--gate` | all methods | all_ok |

Build items (`build`, gate `cells_prep`) are infrastructure, not requirement evidence; a failed
build makes the dependent simulation items fail.

## Coverage gaps (stated limits)

- Single-clock formal model: flop clocking (positive edge, on `clk` after buffer collapse) is
  checked structurally (R11), not by the formal engines. A clock-gated implementation (for
  example an ICG cell for power) is rejected by R11; the requirements for a reviewed extension
  are recorded in SPEC §7.
- Gate-level formal uses the liberty model of the flop, simulation the Verilog UDP; the two
  are not proven equivalent to each other, but both views must pass the contract.
- `sim_onestep` is exhaustive only over the declared subspace (labelled `pass-sampled`); the full
  one-step space is covered by the proofs.
- X/Z inputs are not specified. X on M after a load is seen by Icarus and, in practice, formal;
  Verilator results are 2-state (SPEC §8).
- The negative controls check the formal flow only. DUT mutation testing is assigned to the
  independent verifier (Agent 2).
