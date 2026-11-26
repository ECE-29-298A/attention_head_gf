# exp_lut: requirements traceability matrix

Requirements are defined in `SPEC.md` §3. Item IDs are the `id` fields in `results.json`;
logs are `logs/<id>.log`, SBY and EQY work dirs are `formal/runs/exp_lut_<task>/` and
`formal/runs/eqy_rtl*/` (both git-ignored). Regenerate everything with `./run_all.sh`. A new
implementation is checked with `./run_all.sh --rtl FILE --out DIR` (RTL, both REGISTERED values)
or `--gate --rtl NETLIST [--registered N] --out DIR` (gate level, one value); those runs never
write here. Gate mode names the EQY item `eqy_rtl` (one configuration).

Evidence kinds (user decision D9b, SPEC §4): **edge/spot** = directed edge cases plus 100,000
fixed-seed spot checks on Verilator and Icarus 4-state (`edge_r*`, label `pass-sampled`);
**EQY** = equivalence proof against the golden (`eqy_rtl*`, `proven`); **proof** = SBY
k-induction and abc pdr (`proven`); **static** = Yosys/Verilator structure, interface and lint
(`pass-static`). `smoke_*` items are non-gating and are listed only as supporting evidence.
There is no exhaustive simulation.

| Req | Requirement (short) | Gating evidence (item IDs; assertion / class names) | Kind | Expected status |
|---|---|---|---|---|
| R1 | W = f(D, shift) | r0: `edge_r0` (105,418 points, every shift), `eqy_rtl_r0` (full combinational equivalence with the golden). r1: `fv_prove_r1`, `fv_pdr_r1` (`a_load`, `a_step_W`, `a_seq`: every D and shift), `edge_r1`, `eqy_rtl_r1`. Model: `selftest`. | edge/spot + EQY + proof | pass-sampled, proven |
| R2 | D' rounds half up; shift 0 exact | `edge_r*` classes `half_way` (`k·2^s ± 1`, `(2k+1)·2^(s−1)` −1/0/+1 at every shift) and `dprime_edge`; `fv_sanity_trunc_r1` (truncating reference refuted); `eqy_rtl_*`; `selftest` (ties at every shift) | edge/spot + EQY + proof | pass-sampled, proven |
| R3 | W > 0 iff D' <= 24; zero region; monotone in D | **targeted** in `edge_r*`: `W = 0 ⇔ D' >= 25` at every point (105,418), local monotonicity `W(D+1) <= W(D)` (105,386 checks); classes `dprime_edge` (D' = 24/25 edge), `transition` (every D' where W changes), `last_nonzero`; `eqy_rtl_*`; `selftest` (monotone bound) | edge/spot + EQY | pass-sampled |
| R4 | W = 0 for D >= 2^20, incl. D[21] = 1 | **targeted** in `edge_r*`: `D >= 2^20 → W = 0` (32,791 points); classes `fixed` (2^20 ± 1, 2^21 ± 1, 2^22 − 1), `d20_set`, `d21_set`, `d21_d20_set` (D[21] over low bits that alone give every D'); `eqy_rtl_*`; r1 proofs (`a_load`) | edge/spot + EQY + proof | pass-sampled, proven |
| R5 | 8-bit unsigned, no X/Z for known inputs | Icarus part of `edge_r0`, `edge_r1` (`!==` at every point; `m_xdef` killed there); port width (`lint_r*`) | edge/spot (4-state) + static | pass-sampled |
| R6 | r0: combinational, independent of clk/rst_n/start, no state | `edge_r0` (clk, rst_n, start pseudo-random at every point on both simulators); `eqy_rtl_r0`; `lint_r0` (0 state bits) | edge/spot + EQY + static | pass-sampled, proven |
| R7 | r0: done == start | `edge_r0` (every point); `eqy_rtl_r0` | edge/spot + EQY | pass-sampled, proven |
| R8 | r1: synchronous reset clears done and W, wins over start | `fv_prove_r1`, `fv_pdr_r1` (`a_rst`, `a_step_*`); cover `c_rst_start`; `eqy_rtl_r1`; `edge_r1` (reset with start = 1 every 1,024 points) | proof | proven |
| R9 | r1: load f(D, shift) at the start edge, latency 1 | `fv_prove_r1`, `fv_pdr_r1` (`a_load`, `a_step_W`); covers `c_load_new`, `c_load_zero`, `c_pre_rst_ld`, `c_b2b`; `fv_sanity_lat0_r1` (zero-latency reference refuted) | proof | proven |
| R10 | r1: hold without start; no comb path; no falling-edge change | `fv_prove_r1`, `fv_pdr_r1` (`a_hold`, `a_step_W`: compared with registered references while the current inputs are free); covers `c_hold_diff`, `c_hold3`; comb-path and falling-edge checks in `edge_r1` | proof | proven |
| R11 | r1: after reset, W = f at the last load, else 0 | `fv_prove_r1`, `fv_pdr_r1` (`a_seq`, shadow register with formulation wB); cover `c_w255` | proof | proven |
| R12 | r1: done' = rst_n && start | `fv_prove_r1`, `fv_pdr_r1` (`a_step_done`, `a_rst`, `a_load`, `a_hold`); covers `c_done_pulse`, `c_b2b` | proof | proven |
| R13 | r1: no initial value; rules hold from any state | `fv_prove_r1`, `fv_pdr_r1` (step assertions from step 1 with the DUT state free at step 0); `fv_sanity_pu_r1` (power-up W really free); cover `c_pu_nonzero`; `lint_r1` (no `init`); `.sby` init guard in every `fv_*` run. Supporting smoke: `smoke_powerup_r1`, `smoke_seq_r1` | proof + static | proven |
| R14 | ports; parameter REGISTERED, default 1 | `lint_r0`, `lint_r1` (`lint/check_interface.py`; RTL `lint_r1` also elaborates the default parameter and requires the REGISTERED = 1 structure) | static | pass-static |
| R15 | r0: no state; r1: 9 posedge flops on clk (after buffer collapse), no async reset/latch/memory/init/loop/black box | `lint_r0`, `lint_r1` (Yosys `check -assert`, `scc` empty, forbidden state types, `check_interface.py`); `.sby` guards in every `fv_*` run; `gate/evidence/clkbuf_r1/` (a CTS clock buffer passes) | static | pass-static |
| R16 | lint clean | `lint_r0`, `lint_r1` (Verilator `-Wall`, `lint/check_lint.py`; RTL: no waivers; gate: PDK-model warnings and the r0 port waiver only) | static | pass-static |
| R17 | controller use: r0, start = 0, D in [0, 2,088,960] | subset of R1, R6, R7: `edge_r0` (class `fixed` holds 2,088,960 and +1; a quarter of the spot checks are in the consumed range; start = 0 at about half the points), `eqy_rtl_r0` (all inputs) | edge/spot + EQY | pass-sampled, proven |
| R18 | model agrees with `python/src/attention_model.py` | `selftest` (33,251 sampled points, 0 mismatches) | model (static) | pass-static |
| — | model data generated from the definition | `gen` (interval file, edge file, formal include, vectors; SHA-256 in the log; copies of `iv.txt` and `ref_table.vh` in `logs/`) | infrastructure | pass-static |
| — | checker sanity | `fv_sanity_pu_r1`, `fv_sanity_trunc_r1`, `fv_sanity_lat0_r1` (must fail; traces in `formal/runs/exp_lut_sanity_*/engine_0/trace.vcd`) | negative control | failed-as-expected |
| — | proofs not vacuous | `fv_prove_r1`, `fv_pdr_r1` show 6 asserts (`formal/count_props.py`); `fv_cover_r1`: 10/10 reached, 6 asserts in the model; the antecedents of `a_rst`, `a_load`, `a_hold`, `a_seq` are each reached by a cover; no assumptions | cover + model inspection | covered (bounded-pass) |
| — | gate-level reuse (Phase 2+) | `gate/evidence/golden_r0_gf180/`, `gate/evidence/golden_r1_gf180/` (golden mapped to GF180), `gate/evidence/clkbuf_r1/` (with a CTS-style clock buffer): `results.json` all_ok | all methods | all_ok |

Build items (`build_r*`, gate `cells_prep`) are infrastructure for the edge item.

## Coverage gaps (stated limits)

- **The combinational function at REGISTERED = 0 is not proven by this harness** (D9b). The
  edge/spot item checks 105,418 points per configuration (directed classes plus 100,000
  fixed-seed spot checks); the full-input-space statement for a candidate rests on
  `eqy_rtl_r0` / `eqy_rtl` (equivalence with the golden, which this item set characterises).
  A candidate whose state or structure prevents EQY from matching needs its own reviewed
  equivalence.
- X-freedom is checked by Icarus at the edge/spot points only, not over the whole input space.
  EQY treats X constants as free values, so it is not an X check.
- Single-clock formal model: flop clocking (positive edge, on `clk` after buffer collapse) is
  checked structurally (R15), not by the formal engines. Clock gating is rejected (max_reg
  SPEC §7 lists the reviewed extension it would need).
- Gate-level formal and EQY use the liberty model of the flop, simulation the Verilog UDP; the
  two are not proven equivalent to each other, but both views must pass. Combinational cells
  use the same PDK Verilog model in every view (library trust).
- The two formal references (wA, wB) share one generated include (`ref_table.vh`), computed by
  the model from the definition, never from the RTL.
- The D[21] / D >= 2^21 region is a don't-care of the chip but is specified by this contract
  (SPEC §2); relaxing it needs a reviewed amendment.
- Smoke simulations are non-gating; a smoke failure with all gating items passing would point
  at the testbench or the simulation model and must be investigated, but does not fail the run.
- The negative controls check the formal flow only. DUT mutation testing is assigned to the
  independent verifier (Agent 2); `evidence/smoke_mutants/` is only Agent 1's smoke check.
