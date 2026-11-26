# max_reg Phase 1: independent review of Agent 1's verification contract (Agent 2)

Scope: `pd_flow/modules/max_reg/verif/` at HEAD `6708863` (SPEC.md, RTM.md, run_all.sh, model/,
sim/, formal/, lint/, gate/, results.json). No file of Agent 1 was edited; every run used the
frozen `verif/run_all.sh` with `--rtl <file> --out <review dir>` (git status of `verif/` clean
after all runs). Requirements were derived first, before any verif file was read:
[`EXPECTED.md`](EXPECTED.md).

## Verdict: **APPROVE**

The contract is sound and complete for the golden RTL and for pre-CTS mapped GF180 netlists.
No blocking finding. All 35 must-kill mutants (27 RTL, 16 gate-level runs, plus 1 deep-state
RTL mutant) were killed. All 3 survivors were proven equivalent with EQY. Three non-blocking
changes (N1 to N3) should be made as a reviewed amendment **before the contract is used on a
post-CTS netlist** (Phase 4), because it currently fails closed (`inconclusive`) on any clock
buffer.

## 1. Reproduction

| Run | Where | Result |
|---|---|---|
| Clean copy (`git archive HEAD` of verif + golden into the scratchpad), default golden run | scratchpad | 17/17 ok, `all_ok = true`, 22.96 s; every item status and detail identical to `verif/results.json` |
| Frozen script, `--rtl review/golden_copy/max_reg.v --out review/rerun/rtl_golden` | [`rerun/rtl_golden/results.json`](rerun/rtl_golden/results.json) | 17/17 ok (golden copy SHA-256 `d7cdf381…` = `baseline/SHA256SUMS`) |
| Golden RTL resynthesized by me (`verif/gate/synth_gf180.sh`) | `gate_netlists/golden_gf180.v` | byte-identical to Agent 1's `gate/netlists/max_reg_gf180.v` (3,360.85 µm², 22 `dffq_1`) |
| Frozen script `--gate` on that netlist | [`rerun/gate_golden/results.json`](rerun/gate_golden/results.json) | 18/18 ok, 103.3 s |

## 2. Coverage against EXPECTED.md

| EXPECTED | Contract | Assessment |
|---|---|---|
| R1 `first` overrides | SPEC R3, `a_first`, covers, vec | covered, proven |
| R2 signed greater loads | R4, `a_gt`, `a_step` | covered, proven |
| R3 tie holds (port-equivalent to tie-load) | R5, `a_le`; SPEC states the observational equivalence explicitly | covered; `>=` correctly survives (proven equivalent) |
| R4 smaller holds | R4, `a_le` | covered, proven |
| R5 `!en` holds for any `first`/`S_in` | R2, `a_hold`, covers `c_en0_*` | covered, proven (m06, m10 killed) |
| R6 signed corners, in-context extremes 2^20 and −1,040,384 | corner set includes SCORE_MIN/MAX and ±2^20 neighbours; proofs over all 2^44 pairs | covered |
| R7 all 22 bits | `a_step` bitwise | covered (m08, m27, g02 killed) |
| R8 registered output, no latch/negedge/gated clock | R6 (via `a_step`) + R11 structure + sim comb-path/negedge checks | covered (m12, m13, m18, m19, m20, g03, g04 killed) |
| R9 power-up independence | R8: two-copy miter `a_pu`, free power-up, `sanity_pu` | covered, proven; I confirmed abc pdr also sees a free power-up M (frame-0 counterexample to `M == M2`, `formal_checks/depth1_and_pdr_powerup/pu_pdr.log`) |
| R10 sequence max | R7, shadow `mx` with a second compare formulation; Python list-based model | covered, proven |
| R11 interface | R9 | covered (m25 killed) |
| Added reset | an added port fails R9; an `initial` value fails R11 (and the `.sby` init guard); a reset on an existing input fails R2 | stricter than EXPECTED for `initial` (which is behaviourally harmless after a load). **Agreed**: GF180 flops have no power-up value, so an init attribute is a synthesis/sim mismatch. |
| Assumptions | none (`assume`/`restrict`/`anyconst`/`anyseq` absent; verified by reading the harness and `.sby`) | no overconstraint; the in-context range U5 is **not** assumed |
| Gate level | `--gate`, both flop views | covered, with N1 |

Nothing in EXPECTED.md is missing from the contract.

## 3. Audit findings

Severity: **B** = blocking, **NB** = non-blocking. No B findings.

### Golden model and references: independent and correct (no finding)
- `model/golden_model.py` uses Python ints with explicit two's-complement conversion and a
  **list** `max()` for sequences (a different formulation from the step rule). The KATs are
  hand-derived; I checked all 18 against EXPECTED.md. The self-test cross-checks step and list models on 3,000 sequences.
- The formal harness uses two compare formulations that differ from the RTL's `>`: offset-binary
  (`{~a[21],a[20:0]}`) and the sign of the 23-bit difference. The Verilator TB uses C int32 sign
  extension. Three independent references; none reuses the RTL expression.

### Proof validity: the "proven (unbounded)" claims hold (no finding)
- **Induction depth.** SPEC claims 1-inductiveness. I reran Agent 1's unchanged harness with
  `depth 1` and got PASS for step, seq and pu ([`formal_checks/depth1_and_pdr_powerup/`](formal_checks/depth1_and_pdr_powerup/status.txt)). Depth 4 is therefore ample.
- **Harness-only init registers** (`pv`, `loaded`, `nacc`, `nhold`, `reloads`, `gap`) only gate
  *when* a property applies; they never drive the DUT. They cannot mask a bug, for these reasons:
  - `a_step` is gated only by `pv`, which is 1 from step 1 on, so every transition is checked, including before any load.
  - In the induction step all observers are free.
  - The `.sby` guard `a:init max_reg_props/* %d` rejects any init in the DUT. m11 is killed by exactly this guard ("selection is not empty: a:init ...").
- **Deep-state bugs are not hidden by depth 4.** m28 has a hidden 10-bit counter and corrupts
  M after 1000 idle cycles. The depth-4 base case returned FAIL, because the DUT's
  uninitialised counter is free at step 0. So the BMC base case effectively starts from every DUT
  state.
- **Single-clock abstraction.** The proofs are sound only for posedge flops clocked by `clk`. That
  premise is enforced by the `.sby` select guards (negedge/async/latch/memory). m13 and g03 are
  rejected by `t:$dff r:CLK_POLARITY=1'b0`, m12 and g04 by the latch types, m21 by a Yosys error.
  It is also enforced by `check_interface.py`. The premise is discharged, not assumed.
- **Vacuity.** Assertion counts are checked per task (5/3/1, cover 9/23), and the 23 covers reach every
  antecedent. Both negative controls are refuted. The negative controls depend on the DUT by
  design: m03 and m07 make `fv_sanity_unsigned` "pass", which correctly reports that the DUT matches the
  wrong (unsigned) reference.

### Labels: honest, fail-closed (two NB wording issues, N2)
- `sim_onestep` is labelled `pass-sampled` (exhaustive over a subspace only), covers are `bounded-pass`
  with their depth, and negative controls are `failed` with `expected_outcome: fail`. This is correct.
- **N2a (NB).** When k-induction does not close (SBY status UNKNOWN, e.g. `fv_prove_pu` on m28),
  the label `inconclusive` is right, but the detail says "tool/infrastructure error".
  It should say "induction did not close (UNKNOWN)".
- **N2b (NB).** When abc pdr returns FAIL but SBY cannot replay the trace (`Could not determine
  aigsmt status`; seen on m28 and on my pdr power-up control), the run is labelled `inconclusive`.
  It should be `failed`: the engine's verdict is FAIL. Both cases are fail-closed (`ok = false`), so
  no bug can pass, but the label understates a real counterexample.

### Gate-level mode: the two flop views
- The netlist text is identical in both views. Only the flop **model** differs: the Verilog UDP in
  Verilator/Icarus, and the Liberty `ff` group in Yosys/SBY. A netlist bug (wrong gate, wrong wire, wrong cell
  type) is therefore visible to both. g01 (nand2 → nor2) and g02 (swapped D pins) were killed by
  sims and proofs; g03 (dffnq) and g04 (latq) were killed by lint, guards and sims; the mapped mutants
  s_m03/m09/m10/m13/m14/m15/m26 were all killed. A disagreement between the two flop models would
  make one view fail (fail-closed), so it cannot hide a bug.
- Residual risk (NB, accepted): combinational cells use the **same** PDK Verilog model in both
  views, while ABC mapped against the Liberty functions. A combinational Verilog-vs-Liberty
  discrepancy would not be seen. This is library trust, common to every flow. Optional extra item:
  EQY of the netlist's Yosys view against the golden RTL. I ran it in under 1 s: PASS on s_m01_ge and
  FAIL on s_m03 ([`equiv/gate_s_m01_ge`](equiv/gate_s_m01_ge/eqy.log), [`equiv/gate_s_m03_unsigned_negctl`](equiv/gate_s_m03_unsigned_negctl/eqy.log)).
- **N1 (NB now; required before Phase 4).** A functionally equivalent netlist with a clock buffer
  (g05: one `clkbuf_1` from `clk` to all flops, as CTS produces) passes lint, the structure check and every
  simulation. It fails **every** formal item as `inconclusive`. SBY's `prep` refuses the
  derived clock ("derived signal \clk_buf ... used as clock, derived clocks are only supported with
  clk2fflogic"). The structure check accepts the buffer because it runs after `flatten; opt_clean`,
  which collapses it. So lint and formal disagree on R11, and a post-CTS netlist can never pass.
  I tested the fix on a copy: inserting `hierarchy -top max_reg_props; flatten; opt_clean` before `prep`
  gives PASS on `prove_step` and `pdr_step` for g05, and `sanity_unsigned` still FAILs as required
  ([`formal_checks/clkbuf_flatten/`](formal_checks/clkbuf_flatten/status.txt)). Caveat: after
  `flatten` the guard `a:init max_reg_props/* %d` selects nothing, so the init guard must run
  before the flatten (see exact change below).
- The gate lint waiver is correctly limited: only lines after the end-of-netlist marker, plus
  DECLFILENAME, are waived. I inspected the 9 waived warnings: IMPLICIT, BLKSEQ, UNDRIVEN `notifier`
  and DECLFILENAME, all in the PDK models.
- g08 (`dffrnq_1` with RN tied 1, equivalent) is rejected by R11. That is conservative but consistent with
  "no reset-type flop". Acceptable; it would only matter if a mapper ever chose it.

### Clock-gating rule (R11): justified; what an extension needs (N3, NB)
The rule is justified on four counts. The single-clock SBY model is unsound for a gated clock;
SBY refuses derived clocks anyway; the Liberty file has no function for `icgtp`/`icgtn` (g06 and g07 fail
at `cells_prep`: "liberty has no functional model"); and glitch-freedom and enable timing are STA
properties, not port properties. The rule is also **necessary**: m20 (a hand-made latch+AND gate)
and g06/g07 (ICG) all pass every simulation item, so without R11 they would be judged on simulation
alone. Power motivation is real: g07 (ICG enabled by `en`) is functionally equivalent and stops the
clock on 22 flops for every cycle except the 1-in-1024 `en` cycles.

A reviewed extension (contract amendment, new review) must add all of the following:
1. An allow-list: only `gf180mcu_fd_sc_mcu7t5v0__icgtp_*` with `CLK` = the `clk` net (after buffer collapse) and
   `TE` tied 0. Every flop clock must be either `clk` or such an ICG's `Q`, possibly through
   non-inverting clock buffers. No other logic on any clock net (a hand-made AND/latch gate like m20 stays rejected).
2. A formal ICG model written from the datasheet (latch transparent while CLK low, then AND), validated
   against the PDK Verilog UDP model by exhaustive simulation of its 3 inputs over both clock phases.
3. Formal in `multiclock on` (clk2fflogic) with `clk` as an explicit toggling input. The one new
   assumption allowed is that `clk` alternates. Rerun `a_step`, `a_seq` and `a_pu` with this. The ICG latch has no init, so it joins
   the power-up miter. Keep the negative controls, and add one: E stuck at 0 must fail.
4. An enable-sufficiency property: at every rising edge where the RTL load condition holds, the gated
   clock pulses. This is implied by (3), but should be stated as its own assertion for diagnosis.
5. Mutants for the extension: E stuck 0/1, E missing `first`, E = `S_in > M` only, a hand-made AND
   gate, an ICG on an inverted clock, `TE` floating.
6. Signoff: STA clock-gating setup/hold checks on the ICG enable, enabled in the Phase 4 flow.

### Other observations (NB, informational)
- **Area hint for Phase 2.** `>=` (m01, proven equivalent) maps to 3,088.65 µm² against 3,360.85 µm²
  (−272 µm², −8.1 %) with the `synth_area.py` recipe. Top-level acceptance must use `ll_synth.sh` (orchestrator ruling).
- m17 (a 23-bit subtract rewrite, proven equivalent) is rejected only by R10 lint
  (UNUSEDSIGNAL `d[21:0]`). That is a correct enforcement of the no-waiver lint rule, not a functional rejection.
- Simulation alone would miss m14 (one rare value pair); only the proofs kill it, at RTL and gate level.
  This shows the proofs carry the weight, and the sims are a cross-check.
- m21 (an async clear) is rejected by Yosys at elaboration ("Multiple edge sensitive events"), so its
  formal "kill" is a tool rejection. The sims kill it functionally.

## 4. Mutation testing

The contract was frozen and unmodified. One mutant ran at a time with `--jobs 6` (8-job budget). Raw data:
[`mutation_results.json`](mutation_results.json); per-run results in `mutation_runs/<name>/results.json`.
Driver: [`run_mutants.py`](run_mutants.py). Sources: `mutants/` (RTL), `gate_mutants/` (`g*`:
hand-edited golden netlist; `s_*`: mapped GF180 netlists of RTL mutants via `verif/gate/synth_gf180.sh`).

### Score

| Category | Runs | Killed | Survived | Notes |
|---|---:|---:|---:|---|
| Functional bugs (RTL 21, gate 11) | 32 | **32** | 0 | 32/32 killed by a formal proof item; 30/32 also by simulation (m14, s_m14 are proof-only) |
| Structural / interface violations (init value, latch, reset port) | 3 | **3** | 0 | lint, `.sby` guards; latch also by build |
| **Must-kill total** | **35** | **35** | **0** | **mutation score 100 %** |
| Equivalent, accepted | 3 | 0 | 3 | m01 `>=`, m16 `!(S_in <= M)`, s_m01 mapped `>=`; all **proven equivalent** (EQY) |
| Equivalent, rejected by lint rule | 1 | 1 | 0 | m17 (EQY PASS; UNUSEDSIGNAL) |
| Clock-gating / reset-flop structure (function-preserving; excluded by R11 by design) | 4 | 4 | 0 | m20, g06, g07, g08 |
| Equivalent, buffered clock (should be accepted) | 1 | 1 | 0 | g05: formal `inconclusive`, see N1 |
| **All runs** | **44** | **41** | **3** | 28 RTL + 16 gate-level |

EQY setup: SAT on matched M flops, an unbounded proof for these single-register designs. It
discriminates: the golden copy and the m01, m16, m17 and s_m01 netlists PASS, while m03, m14 and the
s_m03 netlist FAIL ([`equiv/`](equiv/)).

### Per-mutant results

Item key: ind-* = k-induction, pdr-* = abc pdr, ctrl/free/onestep/powerup = Verilator modes,
vec = Verilator + Icarus golden vectors, sanity-* = negative controls (a DUT that matches the wrong
reference makes them "fail").

| # | Mutant | Mode | Description | Class | Outcome | Killed by (items with ok = false) |
|---|---|---|---|---|---|---|
| 1 | `m01_ge` | rtl | > changed to >= (tie loads; port-equivalent) | equivalent | survived (17/17 ok) | none; equivalence: `equiv/m01_ge` PASS |
| 2 | `m02_lt` | rtl | > changed to < (running minimum) | functional-bug | killed (7/17 ok) | vec, ctrl, free, onestep, powerup, cover, pdr-seq, pdr-step, ind-seq, ind-step |
| 3 | `m03_unsigned` | rtl | unsigned compare | functional-bug | killed (6/17 ok) | vec, ctrl, free, onestep, powerup, cover, pdr-seq, pdr-step, ind-seq, ind-step, sanity-uns |
| 4 | `m04_first_ignored` | rtl | first ignored | functional-bug | killed (4/17 ok) | lint, vec, ctrl, free, onestep, powerup, cover, pdr-pu, pdr-seq, pdr-step, ind-pu, ind-seq, ind-step |
| 5 | `m05_en_ignored` | rtl | en ignored | functional-bug | killed (6/17 ok) | lint, vec, ctrl, free, onestep, powerup, cover, pdr-seq, pdr-step, ind-seq, ind-step |
| 6 | `m06_prec_swap` | rtl | en/first precedence swapped: first loads without en | functional-bug | killed (7/17 ok) | vec, ctrl, free, onestep, powerup, cover, pdr-seq, pdr-step, ind-seq, ind-step |
| 7 | `m07_signbit` | rtl | sign-bit fault: sign-differing pairs decided inverted (positive S vs negative M holds, negative S vs positive M loads) | functional-bug | killed (6/17 ok) | vec, ctrl, free, onestep, powerup, cover, pdr-seq, pdr-step, ind-seq, ind-step, sanity-uns |
| 8 | `m08_stuck0_b13` | rtl | stuck-at-0 on stored bit 13 | functional-bug | killed (7/17 ok) | vec, ctrl, free, onestep, powerup, cover, pdr-seq, pdr-step, ind-seq, ind-step |
| 9 | `m09_cmp21` | rtl | compare done on 21 bits (bit 21 dropped, bit 20 treated as sign) | functional-bug | killed (7/17 ok) | vec, ctrl, free, onestep, powerup, cover, pdr-seq, pdr-step, ind-seq, ind-step |
| 10 | `m10_reset_first` | rtl | added clear on first while en = 0 (reset-like, uses existing input) | functional-bug | killed (8/17 ok) | vec, ctrl, free, onestep, powerup, pdr-seq, pdr-step, ind-seq, ind-step |
| 11 | `m11_initval` | rtl | power-up initial value M = 0 (no port change) | structural-or-interface-violation | killed (6/17 ok) | lint, powerup, cover, pdr-pu, pdr-seq, pdr-step, ind-pu, ind-seq, ind-step, sanity-pu, sanity-uns |
| 12 | `m12_latch` | rtl | transparent-high latch instead of a flop | structural-or-interface-violation | killed (1/17 ok) | lint, build, vec, ctrl, free, onestep, powerup, cover, pdr-pu, pdr-seq, pdr-step, ind-pu, ind-seq, ind-step, sanity-pu, sanity-uns |
| 13 | `m13_negedge` | rtl | negedge flop | functional-bug | killed (2/17 ok) | lint, vec, ctrl, free, onestep, powerup, cover, pdr-pu, pdr-seq, pdr-step, ind-pu, ind-seq, ind-step, sanity-pu, sanity-uns |
| 14 | `m14_rare_pair` | rtl | fault for one rare pair only: S_in = 0x0A5C3E vs M = 0x0A5C3D (adjacent, both positive) does not load | functional-bug | killed (13/17 ok) | pdr-seq, pdr-step, ind-seq, ind-step |
| 15 | `m15_minneg` | rtl | fault only when M is the most-negative value: nothing beats MINNEG | functional-bug | killed (9/17 ok) | vec, free, onestep, cover, pdr-seq, pdr-step, ind-seq, ind-step |
| 16 | `m16_equiv_not_le` | rtl | equivalent rewrite !(S_in <= M) | equivalent | survived (17/17 ok) | none; equivalence: `equiv/m16_equiv_not_le` PASS |
| 17 | `m17_equiv_sub` | rtl | equivalent rewrite: sign of 23-bit difference | equivalent | killed (16/17 ok) | lint; equivalence: `equiv/m17_equiv_sub` PASS |
| 18 | `m18_comb_bypass` | rtl | combinational bypass: M shows S_in in the same cycle on a first load | functional-bug | killed (7/17 ok) | vec, ctrl, free, onestep, powerup, cover, pdr-seq, pdr-step, ind-seq, ind-step |
| 19 | `m19_twocycle` | rtl | two-cycle latency (extra pipeline stage; 44 flops) | functional-bug | killed (5/17 ok) | lint, vec, ctrl, free, onestep, powerup, pdr-pu, pdr-seq, pdr-step, ind-pu, ind-seq, ind-step |
| 20 | `m20_clkgate` | rtl | clock-gated (latch-based ICG style): functionally correct; contract rejects by R11 | clock-gating | killed (1/17 ok) | lint, build, vec, ctrl, free, onestep, powerup, cover, pdr-pu, pdr-seq, pdr-step, ind-pu, ind-seq, ind-step, sanity-pu, sanity-uns |
| 21 | `m21_async_rst` | rtl | async clear on first (no new port) | functional-bug | killed (2/17 ok) | lint, vec, ctrl, free, onestep, powerup, cover, pdr-pu, pdr-seq, pdr-step, ind-pu, ind-seq, ind-step, sanity-pu, sanity-uns |
| 22 | `m22_minneg_tie` | rtl | MINNEG over MAXPOS wrongly loads (overflow-style compare fault on one pair) | functional-bug | killed (9/17 ok) | vec, free, onestep, cover, pdr-seq, pdr-step, ind-seq, ind-step |
| 23 | `m23_sub_overflow` | rtl | compare by 22-bit subtraction sign (overflow not handled) | functional-bug | killed (6/17 ok) | lint, vec, ctrl, free, onestep, powerup, cover, pdr-seq, pdr-step, ind-seq, ind-step |
| 24 | `m24_first_onlyhigh` | rtl | first only overrides for non-negative S_in | functional-bug | killed (5/17 ok) | vec, ctrl, free, onestep, powerup, cover, pdr-pu, pdr-seq, pdr-step, ind-pu, ind-seq, ind-step |
| 25 | `m25_rst_port` | rtl | added synchronous active-low reset port (interface change; power-up behaviour defined) | structural-or-interface-violation | killed (7/17 ok) | lint, ctrl, onestep, powerup, pdr-pu, pdr-seq, pdr-step, ind-pu, ind-seq, ind-step |
| 26 | `m26_cmp_nolsb` | rtl | compare ignores bit 0 (S_in = M+1 with even M holds) | functional-bug | killed (9/17 ok) | vec, ctrl, free, onestep, pdr-seq, pdr-step, ind-seq, ind-step |
| 27 | `m27_stuck1_b21` | rtl | stuck-at-1 on stored sign bit 21 | functional-bug | killed (7/17 ok) | vec, ctrl, free, onestep, powerup, cover, pdr-seq, pdr-step, ind-seq, ind-step |
| 28 | `gate_g01_nand2_to_nor2` | gate | cell _155_ nand2_1 replaced by nor2_1 (wrong gate in compare logic) | functional-bug | killed (9/18 ok) | vec, ctrl, free, onestep, powerup, pdr-seq, pdr-step, ind-seq, ind-step |
| 29 | `gate_g02_dswap_b0_b1` | gate | D inputs of flops M[0] and M[1] swapped | functional-bug | killed (9/18 ok) | vec, ctrl, free, onestep, powerup, pdr-seq, pdr-step, ind-seq, ind-step |
| 30 | `gate_g03_dffnq_b0` | gate | flop M[0] replaced by negative-edge dffnq_1 | functional-bug | killed (3/18 ok) | lint, vec, ctrl, free, onestep, powerup, cover, pdr-pu, pdr-seq, pdr-step, ind-pu, ind-seq, ind-step, sanity-pu, sanity-uns |
| 31 | `gate_g04_latq_b4` | gate | flop M[4] replaced by latch latq_1 (E = clk, transparent high) | functional-bug | killed (4/18 ok) | lint, vec, ctrl, free, onestep, cover, pdr-pu, pdr-seq, pdr-step, ind-pu, ind-seq, ind-step, sanity-pu, sanity-uns |
| 32 | `gate_g05_clkbuf` | gate | all flops clocked through one clkbuf_1 from clk (equivalent; models a post-CTS netlist) | equivalent | killed (9/18 ok) | cover, pdr-pu, pdr-seq, pdr-step, ind-pu, ind-seq, ind-step, sanity-pu, sanity-uns |
| 33 | `gate_g06_icg_const` | gate | all flops clocked through icgtp_1 with E = 1 (equivalent; clock-gating structure) | clock-gating | killed (7/18 ok) | cells_prep, lint, cover, pdr-pu, pdr-seq, pdr-step, ind-pu, ind-seq, ind-step, sanity-pu, sanity-uns |
| 34 | `gate_g07_icg_en` | gate | all flops clocked through icgtp_1 enabled by en (functionally equivalent power optimisation) | clock-gating | killed (7/18 ok) | cells_prep, lint, cover, pdr-pu, pdr-seq, pdr-step, ind-pu, ind-seq, ind-step, sanity-pu, sanity-uns |
| 35 | `gate_g08_dffrnq_tied` | gate | flop M[0] replaced by dffrnq_1 with RN tied 1 (reset never active; equivalent) | equivalent, structural | killed (8/18 ok) | lint, cover, pdr-pu, pdr-seq, pdr-step, ind-pu, ind-seq, ind-step, sanity-pu, sanity-uns |
| 36 | `gate_s_m01_ge` | gate | mapped GF180 netlist of RTL mutant m01_ge (> changed to >= (tie loads; port-equivalent)) | equivalent | survived (18/18 ok) | none; equivalence: `equiv/gate_s_m01_ge` PASS |
| 37 | `gate_s_m03_unsigned` | gate | mapped GF180 netlist of RTL mutant m03_unsigned (unsigned compare) | functional-bug | killed (7/18 ok) | vec, ctrl, free, onestep, powerup, cover, pdr-seq, pdr-step, ind-seq, ind-step, sanity-uns |
| 38 | `gate_s_m09_cmp21` | gate | mapped GF180 netlist of RTL mutant m09_cmp21 (compare done on 21 bits (bit 21 dropped, bit 20 treated as sign)) | functional-bug | killed (8/18 ok) | vec, ctrl, free, onestep, powerup, cover, pdr-seq, pdr-step, ind-seq, ind-step |
| 39 | `gate_s_m10_reset_first` | gate | mapped GF180 netlist of RTL mutant m10_reset_first (added clear on first while en = 0 (reset-like, uses existing input)) | functional-bug | killed (9/18 ok) | vec, ctrl, free, onestep, powerup, pdr-seq, pdr-step, ind-seq, ind-step |
| 40 | `gate_s_m13_negedge` | gate | mapped GF180 netlist of RTL mutant m13_negedge (negedge flop) | functional-bug | killed (4/18 ok) | lint, vec, ctrl, free, onestep, powerup, cover, pdr-pu, pdr-seq, pdr-step, ind-pu, ind-seq, ind-step, sanity-uns |
| 41 | `gate_s_m14_rare_pair` | gate | mapped GF180 netlist of RTL mutant m14_rare_pair (fault for one rare pair only: S_in = 0x0A5C3E vs M = 0x0A5C3D (adjacent, both positive) does not load) | functional-bug | killed (14/18 ok) | pdr-seq, pdr-step, ind-seq, ind-step |
| 42 | `gate_s_m15_minneg` | gate | mapped GF180 netlist of RTL mutant m15_minneg (fault only when M is the most-negative value: nothing beats MINNEG) | functional-bug | killed (10/18 ok) | vec, free, onestep, cover, pdr-seq, pdr-step, ind-seq, ind-step |
| 43 | `gate_s_m26_cmp_nolsb` | gate | mapped GF180 netlist of RTL mutant m26_cmp_nolsb (compare ignores bit 0 (S_in = M+1 with even M holds)) | functional-bug | killed (10/18 ok) | vec, ctrl, free, onestep, pdr-seq, pdr-step, ind-seq, ind-step |
| 44 | `m28_deep_counter` | rtl | deep-state bug: after 1000 consecutive en = 0 cycles, M bit 3 flips once (hidden 10-bit counter) | functional-bug | killed (10/17 ok) | lint, ctrl, pdr-seq, pdr-step, ind-pu, ind-seq, ind-step |

## 5. Exact changes (non-blocking; one reviewed amendment, before any post-CTS / Phase 4 netlist run)

**N1 — accept non-inverting clock buffers in formal, keep the init guard sound**
(`verif/formal/max_reg.sby`, `[script]`). Replace
```
prep -top max_reg_props
```
with
```
hierarchy -top max_reg_props
select -assert-none a:init max_reg_props/* %d
flatten
opt_clean
prep -top max_reg_props
```
and delete the later `select -assert-none a:init max_reg_props/* %d` line. That guard must run
before `flatten`, because afterwards every wire lives in `max_reg_props`. Keep the type/polarity
guards after `prep` (they still see every flop). Then add g05 (`review/gate_mutants/g05_clkbuf.v`)
as a must-pass gate check and g03 as a must-fail check, and rerun the golden RTL and gate evidence.
State in SPEC R11 that "clocked by `clk`" means after collapsing buffers, so the lint check and
formal agree.

**N2 — label details** (`verif/run_all.sh`, `sby)` case):
(a) for `sstat == UNKNOWN`, set `det="induction did not close (UNKNOWN)"`, keeping `st=inconclusive`;
(b) if the log contains `returned FAIL` from an engine, set `st=failed` even when SBY ends in
ERROR because of trace replay (`Could not determine aigsmt status`), and keep the engine line in `det`.

**N3 — record the clock-gating extension requirements** (section 3) in SPEC §4 under
"Coverage gaps", so a later power optimisation has a defined path. No change to the current rule.

Optional: add a gate-mode item `eqy_rtl` (EQY of the Yosys view against the golden RTL, as in
`review/equiv/gate_s_m01_ge/eq.eqy`). It is an independent full-function check of the netlist and takes under 1 s.

## 6. Files

- `EXPECTED.md`: requirements derived before reading the contract
- `REVIEW.md`: this file
- `mutation_results.json`: every mutant run, class, killing items, equivalence proofs, summary
- `mutants/` (28 RTL), `gate_mutants/` (16 netlists + stat files), `gate_netlists/golden_gf180.v`
- `mutation_runs/<name>/`: frozen-contract output per mutant (logs and formal dirs are git-ignored)
- `rerun/rtl_golden/`, `rerun/gate_golden/`: my reruns of the golden evidence
- `equiv/`: EQY proofs (`run_eqy.sh`, `template.eqy`, logs)
- `formal_checks/`: depth-1 induction, the pdr power-up control, the clock-buffer flatten fix
- `golden_copy/max_reg.v`: hash-checked copy of the golden RTL
- `run_mutants.py`: mutation driver
