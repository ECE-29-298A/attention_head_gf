# exp_lut: requirements traceability matrix

Requirements are defined in `SPEC.md` §3. Item IDs are the `id` fields in `results.json`;
logs are `logs/<id>.log`, SBY work dirs (status, engine logs, cover and counterexample traces)
are `formal/runs/exp_lut_<task>/` (both git-ignored). All paths are relative to this directory.
Regenerate everything with `./run_all.sh`. A new implementation is checked with
`./run_all.sh --rtl FILE --out DIR` (RTL, both REGISTERED values) or
`--gate --rtl NETLIST [--registered N] --out DIR` (gate level, one value); those runs never
write here. The `label` column of `results.json` gives the standard label (SPEC §5).
`ivl_exh_r{0,1}_*` stands for the four Icarus items `_s0_3`, `_s4_7`, `_s8_11`, `_s12_15`.

| Req | Requirement (short) | Evidence (results.json item IDs; assertion / cover names) | Method | Expected status |
|---|---|---|---|---|
| R1 | W = f(D, shift) for all 2^26 pairs | `fv_equiv_r0`, `fv_pdr_equiv_r0` (`a_wA`, `a_wB`: two formal references, every input); `fv_prove_r1`, `fv_pdr_r1` (`a_load`, `a_step_W`, `a_seq`) | proof (complete for r0) | proven |
| | | `sim_exh_r0`, `sim_exh_r1` (Verilator, all 2^26, two references each); `ivl_exh_r0_*`, `ivl_exh_r1_*` (Icarus 4-state, all 2^26) | exhaustive simulation | pass-exhaustive |
| | | `selftest` (KATs, two D' formulations, interval consistency) | model self-check | pass-static |
| R2 | D' rounds half up; shift 0 exact | as R1, plus covers `fv_cover_r0` (a tie rounded up at each shift 1..15); `fv_sanity_trunc_r0` (truncating reference refuted); `selftest` (ties at every shift); `vec_r1` (every threshold −1/0/+1 at every shift) | proof + cover + sim | proven |
| R3 | W > 0 iff D' <= 24; zero region; monotone | as R1; covers `fv_cover_r0` (every D' 0..25 with its W, last non-zero / first zero at shift 15); `selftest` (monotone, bound 255·e^−6.25 < 1/2, interval file strictly decreasing) | proof + cover + sim | proven |
| R4 | W = 0 for D >= 2^20, incl. D[21] = 1 | as R1 (full 22-bit D); covers `c_d20`, `c_d21`; `fv_sanity_d21_r0` (reference ignoring D[21] refuted) | proof + cover + sim | proven |
| R5 | 8-bit unsigned, no X/Z for known inputs | port width (`lint`); `ivl_exh_*` and `vec_r1` compare with `!==` on every point | static + 4-state sim | pass-exhaustive |
| R6 | r0: combinational, independent of clk/rst_n/start, no state | `fv_equiv_r0`, `fv_pdr_equiv_r0` (W asserted at every step against the current inputs, clk/rst_n/start free); `sim_exh_r0`, `ivl_exh_r0_*` (clk, rst_n, start varied at every point); `lint_r0` (0 state bits) | proof + sim + static | proven |
| R7 | r0: done == start | `fv_equiv_r0`, `fv_pdr_equiv_r0` (`a_done`); covers `c_done1`, `c_done0`; `sim_exh_r0`, `ivl_exh_r0_*` | proof + sim | proven |
| R8 | r1: synchronous reset clears done and W, wins over start | `fv_prove_r1`, `fv_pdr_r1` (`a_rst`, `a_step_*`); cover `c_rst_start`; `sim_exh_r1` (reset with start = 1 every 4,096 loads); `ivl_exh_r1_*`; `sim_seq_r1`; `vec_r1` | proof + cover + sim | proven |
| R9 | r1: load f(D, shift) at the start edge, latency 1 | `fv_prove_r1`, `fv_pdr_r1` (`a_load`, `a_step_W`); covers `c_load_new`, `c_load_zero`, `c_pre_rst_ld`, `c_b2b`; `fv_sanity_lat0_r1` (zero-latency reference refuted); `sim_exh_r1`, `ivl_exh_r1_*` (every pair loaded) | proof + cover + sim | proven |
| R10 | r1: hold without start; no comb path; no falling-edge change | `fv_prove_r1`, `fv_pdr_r1` (`a_hold`, `a_step_W`: W is compared with registered references while D, shift, start are free in the current step); covers `c_hold_diff`, `c_hold3`; comb-path and falling-edge checks on every cycle of `sim_exh_r1`, `sim_seq_r1`, `sim_powerup_r1`, `vec_r1`, `ivl_exh_r1_*` | proof + cover + sim | proven |
| R11 | r1: after reset, W = f at the last load, else 0 | `fv_prove_r1`, `fv_pdr_r1` (`a_seq`, shadow register with formulation wB); cover `c_w255`; shadow checks in `sim_exh_r1`, `sim_seq_r1` | proof + sim | proven |
| R12 | r1: done' = rst_n && start | `fv_prove_r1`, `fv_pdr_r1` (`a_step_done`, `a_rst`, `a_load`, `a_hold`); covers `c_done_pulse`, `c_b2b`; `sim_exh_r1` (hold cycle: done = 0), `ivl_exh_r1_*`, `vec_r1` (done on every cycle) | proof + cover + sim | proven |
| R13 | r1: no initial value; rules hold from any state | `fv_prove_r1`, `fv_pdr_r1` (step assertions from step 1 with the DUT state free at step 0); `fv_sanity_pu_r1` (power-up W really free); cover `c_pu_nonzero`; `sim_powerup_r1` (64 random states, identical traces after reset); `sim_seq_r1` (step rule before the first reset); `lint_r1` (no `init` attribute); `.sby` init guard in every `fv_*` run | proof + sim + static | proven |
| R14 | ports; parameter REGISTERED, default 1 | `lint_r0`, `lint_r1` (`lint/check_interface.py` on the Yosys JSON; RTL `lint_r1` also elaborates the default parameter and requires the REGISTERED = 1 structure) | static | pass-static |
| R15 | r0: no state; r1: 9 posedge flops on clk (after buffer collapse), no async reset/latch/memory/init/loop/black box | `lint_r0`, `lint_r1` (Yosys `check -assert`, `scc` empty on the unoptimised netlist, forbidden state types, `check_interface.py`); `.sby` guards in every `fv_*` run; `gate/evidence/clkbuf_r1/` (a CTS clock buffer passes) | static | pass-static |
| R16 | lint clean | `lint_r0`, `lint_r1` (Verilator `-Wall`, `lint/check_lint.py`; RTL: no waivers; gate: PDK-model warnings and the r0 port waiver only) | static | pass-static |
| R17 | controller use: r0, start = 0, D in [0, 2,088,960] | subset of R1, R6, R7 (proven for every D, every shift, start free) | proof | proven |
| R18 | model agrees with `python/src/attention_model.py` | `selftest` (33,251 points, 0 mismatches) | model self-check | pass-static |
| — | model data generated from the definition | `gen` (interval file, formal include, vectors; SHA-256 in the log; copies in `logs/`) | infrastructure | pass-static |
| — | checker sanity | `fv_sanity_trunc_r0`, `fv_sanity_d21_r0`, `fv_sanity_pu_r1`, `fv_sanity_lat0_r1` (must fail; traces in `formal/runs/exp_lut_sanity_*/engine_0/trace.vcd`) | negative control | failed-as-expected |
| — | proofs not vacuous | every `fv_equiv_*`/`fv_prove_*`/`fv_pdr_*` detail shows the expected assertion count (3 for r0, 6 for r1; `formal/count_props.py`); `fv_cover_r0`: 47/47 reached, 3 asserts in the model; `fv_cover_r1`: 10/10 reached, 6 asserts; the antecedents of `a_rst`, `a_load`, `a_hold`, `a_seq` are each reached by a cover; no assumptions | cover + model inspection | covered (bounded-pass) |
| — | gate netlist equivalent to the golden RTL (gate mode) | `eqy_rtl` (EQY, sat, depth 1, golden with `chparam REGISTERED N`; `formal/runs/eqy_rtl/`) | equivalence proof | proven |
| — | gate-level reuse (Phase 2+) | `gate/evidence/golden_r0_gf180/results.json`, `gate/evidence/golden_r1_gf180/results.json` (golden mapped to GF180), `gate/evidence/clkbuf_r1/results.json` (with a CTS-style clock buffer) | all methods | all_ok |

Build items (`build_r*`, gate `cells_prep`) are infrastructure, not requirement evidence; a
failed build makes the dependent simulation items fail.

## Coverage gaps (stated limits)

- Single-clock formal model: flop clocking (positive edge, on `clk` after buffer collapse) is
  checked structurally (R15), not by the formal engines. Clock gating is rejected (max_reg
  SPEC §7 lists the reviewed extension it would need).
- Gate-level formal and EQY use the liberty model of the flop, simulation the Verilog UDP; the
  two are not proven equivalent to each other, but both views must pass. Combinational cells
  use the same PDK Verilog model in every view (library trust).
- The REGISTERED = 1 Icarus exhaustive items check the hold behaviour after every 16th load
  only (cost); the hold after every load is checked by `sim_exh_r1` (Verilator) and proven.
- X/Z inputs are not specified. Verilator results are 2-state; X-freedom rests on Icarus
  (SPEC §7).
- The formal references share one generated include (`ref_table.vh`) with each other; it is
  computed by the model from the definition, never from the RTL, and the simulations use the
  model's interval file plus an in-TB double-precision formula.
- The D[21] / D >= 2^21 region is a don't-care of the chip but is specified by this contract
  (SPEC §2); relaxing it needs a reviewed amendment.
- The negative controls check the formal flow only. DUT mutation testing is assigned to the
  independent verifier (Agent 2).
