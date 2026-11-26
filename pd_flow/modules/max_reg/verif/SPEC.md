# max_reg: verification specification

Design under test: `pd_flow/baseline/original_rtl/max_reg.v` (golden; never edited). Any later
implementation is checked against this same contract with `run_all.sh --rtl FILE --out DIR`;
a gate-level netlist with `run_all.sh --rtl NETLIST --gate --out DIR` (section 6).
Sources used to derive the requirements: the RTL header and body, the instance in
`pd_flow/baseline/original_rtl/attention_controller.sv` (line 106) and its FSM (lines 120 to 175),
and `PHASE0_AUDIT.md` invariant 2. The structure follows the approved `ripple_add` contract.

## 1. Function

`max_reg` is a 22-bit signed running-maximum register with **no reset**. At each rising edge of
`clk`:

    if (en && (first || S_in > M))  M <= S_in;   // signed 22-bit compare
    else                            M <= M;

`first` marks the first score of a query and loads it unconditionally, so no reset or
sentinel value is needed. The comparator and register structure are implementation choices
and are **not** part of the contract; only the behaviour at the ports is.

## 2. Use in the design

```
max_reg max_unit (.clk(clk), .first(token == 4'd0), .en(score_done && !second_pass),
                  .S_in(score), .M(maximum));
```

| Signal | Driven by | What the controller relies on |
|---|---|---|
| `first` | `token == 0`, a **level**: high from the start of a run until the edge that accepts key 0, high again during pass 2 key 0 and in IDLE | it only matters together with `en`; `first` with `en = 0` must do nothing |
| `en` | `score_done && !second_pass`, a one-cycle pulse per key in pass 1; never high in pass 2 or in a continue run (`second_pass <= cont`) | M holds for an arbitrarily long time when `en = 0` (pass 2, V accumulation, division, output, continue runs, which reuse the previous query's M) |
| `S_in` | `score` from `mac_unit` (`S`): partial MAC sums while `en = 0`, the finished score on the `en` cycle; INT8 range −1,040,384 … 1,048,576 | only the `en` cycle's value matters |
| `M` | to `mac_unit.M` (pass 2 subtracts it) | M = max of the query's scores from the cycle after the last key's `en` |

The controller relies on R1 to R8 and R12 below; the contract checks the full 22-bit range,
not only the INT8 range, because the module's own behaviour is specified there.

## 3. Requirements

Values are 22-bit two's complement: MINNEG = 22'h200000 = −2,097,152, MAXPOS = 22'h1FFFFF =
2,097,151. "Load" means a rising edge with `en = first = 1`.

| ID | Requirement |
|---|---|
| R1 | **Update rule.** For every current M and every `first`, `en`, `S_in`, the value of M after a rising `clk` edge is `(en && (first \|\| S_in > M)) ? S_in : M`, with `>` the signed 22-bit order. This holds from power-up, for whatever value M has. |
| R2 | **Hold when `en = 0`.** With `en = 0`, M is unchanged at the edge, whatever `first` and `S_in` are (also `first = 1`, and `S_in > M`). |
| R3 | **`first` overrides the compare.** With `en = first = 1`, M becomes `S_in` for every M, including `S_in < M` and `S_in == M`. |
| R4 | **Signed compare.** With `en = 1, first = 0`, M becomes `S_in` exactly when `S_in > M` in signed order and is unchanged otherwise. This includes the extremes (MINNEG and MAXPOS against each other and against themselves), the sign boundary (−1 against 0, both directions), and every pair whose signed and unsigned orders disagree. |
| R5 | **Tie.** With `en = 1, first = 0, S_in == M`, M is unchanged. (Loading the equal value is indistinguishable at the port; the requirement is `M' == M`.) |
| R6 | **Registered output.** M changes only at a rising `clk` edge: no combinational path from `first`, `en`, `S_in` to M, no change at the falling edge, one cycle of latency. |
| R7 | **Sequence semantics.** After a load, and until the next load, M equals the maximum (signed) of every `S_in` accepted (`en = 1`) since and including that load. Consequences checked separately: between loads M never decreases (it holds or takes a strictly greater `S_in`), and M only ever takes a value that was on `S_in`. |
| R8 | **No reset; power-up independence.** There is no reset input and M has no initial value; its power-up value is arbitrary. Before the first load M is unspecified (only R1 constrains it). After a load, M and every later value of M are the same for every power-up value. |
| R9 | **Interface.** Exactly the ports `clk` (input, 1), `first` (input, 1), `en` (input, 1), `S_in` (input [21:0]), `M` (output [21:0]); no parameter. Names, directions and widths must not change (the controller connects by name). Port signedness is not checked: the controller's connection carries bits, and the signed compare is required by R4. |
| R10 | **Lint.** RTL: `verilator --lint-only -Wall` gives no warning and no error (no waivers). Gate level: no warning located in the netlist (section 6 for the PDK-model warnings). |
| R11 | **Structure.** Exactly 22 flop bits; every flop is a positive-edge D flop (with or without enable) with no synchronous or asynchronous reset or set, clocked by the `clk` port, where "clocked by `clk`" means after collapsing non-inverting buffers (`flatten; opt_clean`, as both the lint structure check and the `.sby` do), so a CTS clock buffer from `clk` to the flops is accepted, while an inverted, gated or otherwise derived clock is not; no latches, memories or `$anyinit`; no `init` attribute (power-up value) on any wire; no combinational loops, undriven or multiply-driven nets; no black-box cells. Besides R8, this is a **contract assumption**: the formal model is single-clock (section 4), so a clock-gated or negative-edge implementation is rejected here and needs the reviewed contract extension of section 7. |
| R12 | **Controller use.** Under the stimulus the controller produces (section 2: `first` as a level, one `en` pulse per key with gaps, pass 2 and continue runs with `en = 0`, arbitrary `S_in` while `en = 0`), M after the last key of pass 1 equals the maximum of the query's scores, and M holds that value through pass 2 and through any continue runs. (Follows from R1 to R7; checked with directed stimulus.) |

Out of scope: timing, area and power (Phase 2+ metrics); X/Z **inputs** (not specified; see
section 8 for X on M); multi-clock behaviour (one clock only); clock gating (section 7).

## 4. Verification approach

| Method | What | Strength |
|---|---|---|
| Golden model | `model/golden_model.py`: one-step rule on Python ints (22-bit values converted by explicit subtraction), and a separate sequence model that keeps the **list** of accepted scores and predicts `max(list)` (R7). M is `None` (unknown) until the first load. `selftest`: conversion and hand-computed known-answer tests, and 3,000 random sequences on which the iterated step rule must equal the list maximum. | reference |
| Golden vectors | The model writes a cycle-by-cycle file `first en S_in M` (M = `x` while unknown): power-up preamble without a load (`en = 1`, also `first = 1, en = 0`); every ordered pair of 15 corner values (MINNEG, MINNEG+1, −2, −1, 0, 1, 2, MAXPOS−1, MAXPOS, the INT8 score limits, ±2^20 neighbours) offered with `en = 0`, `first = 1, en = 0`, `en = 1`, and as a load; single-bit differences and ±2^k neighbours at every bit around 8 bases; ties and near ties; monotone runs and back-to-back loads; 3,000 controller-style queries (section 2 pattern, 1 to 16 keys, gaps 0 to 40, ties and max±1 scores, 25 % continue runs); 200,000 unconstrained cycles with regime switching. 558,544 cycles, 558,536 with a known M. Applied on **Verilator** and **Icarus** (4-state, `!==`); each simulator must apply every cycle and check every known value. | sampled |
| Simulation checks every cycle | `sim/tb_max_reg.cpp` (Verilator, all modes): (a) M unchanged after the inputs change with `clk` low and at the falling edge (R6); (b) the one-step rule from the **observed** M, also before any load (R1); (c) an in-TB running-max tracker after a load (R7); (d) the file value in vector mode. `sim/tb_vectors.sv` (Icarus) checks (a) and (d). The Verilator model is built with `--x-initial unique` and run with `randReset(2)`, so the power-up M is random (seeded). | – |
| Controller-style random | `sim_ctrl`: 100 M cycles of controller-pattern queries (gaps up to 1,100 cycles, as the real 1,024-cycle score row), plus a per-query check against `std::max` over the stored list of the query's scores, both after pass 1 and after pass 2 / continue runs (R12). | sampled |
| Unconstrained random | `sim_free`: 100 M cycles, regimes of 50 to 2,000 cycles with `P(first)` in {0, 1/64, 1/8, 1/2, 1}, `P(en)` in {0.05, 0.5, 0.95, 1}, and `S_in` uniform, extreme values, M±3, M itself (ties) or M with one bit flipped, INT8 range, or sparse/dense bit patterns. | sampled |
| Reduced exhaustive one-step | `sim_onestep 6 6`: every (M, S_in, en, first) with M, S_in in V, V = all values whose top 6 bits [21:16] and low 6 bits [5:0] are free and whose middle bits [15:6] are all 0 or all 1 (8,192 values, covering sign, magnitude extremes and near-equal pairs): 268,435,456 one-step checks. Exhaustive **over that subspace only**, so labelled `pass-sampled` (status `pass-exhaustive-subspace`); the full one-step space (2^46) is covered by the proofs. | sampled (exhaustive on V) |
| Power-up independence (sim) | `sim_powerup 64`: 64 models with different random power-up values (all 64 distinct), the same stimulus (200 cycles without a load but with `en`, then a load, then 3,000 cycles); the traces after the load must be identical and correct. | sampled |
| Formal: one-step relation | SBY `mode prove`, harness `formal/max_reg_props.sv` (STEP): `a_step` (M == reference next state, R1) and the decomposed `a_hold` (R2), `a_first` (R3), `a_gt`, `a_le` (R4, R5). The reference next state is computed by the harness from the current M and `S_in` with an offset-binary compare (`{~a[21], a[20:0]} > {~b[21], b[20:0]}`, not the RTL's `>`) and registered. M is unconstrained (no initial value; arbitrary at step 0 and, in the induction step, in every state). Proved by **k-induction** (smtbmc/Z3, depth 4) and independently by **abc pdr**. | proven (unbounded) |
| Formal: sequence | SEQ: a shadow running-max register `mx` in the harness (loaded on `en && first`, updated with a second compare formulation, the sign of the 23-bit difference) and observer `loaded`: `a_seq` `loaded → M == mx` (R7), `a_mono` (without a load M holds or takes a strictly greater `S_in`), `a_src` (M only takes `S_in`). k-induction and abc pdr. | proven (unbounded) |
| Formal: power-up independence | POWERUP: two DUT copies on the same inputs, each with its own unconstrained power-up M: `a_pu` `loaded → M == M2` (R8). k-induction and abc pdr. | proven (unbounded) |
| Covers | SBY `mode cover`, depth 10, all property groups and both copies present (9 asserts checked along the traces), **23 covers**, each observing M: the one-step regions (first loads a lower / equal value, greater updates, tie holds, smaller holds, `en = 0` with a greater `S_in`, `first` without `en`), signed corners (negative vs non-negative both ways, MAXPOS over MINNEG, MINNEG vs MAXPOS, MINNEG and MAXPOS ties, 0 over −1, −1 vs 0, a load of MINNEG over MAXPOS), sequences (3+ accepted with the last below the max, a reload with a lower value, 4 hold cycles, an update before any load, a later key raising M after an `en = 0` gap) and power-up (copies differ at step 0; copies differ and a load makes them equal). Every cover must be reached; `run_all.sh` checks 23 reached, 0 unreached, and the cell counts. | bounded-pass (depth 10) |
| Negative controls | Must be **refuted** with a trace: `sanity_unsigned` (reference with an unsigned compare: shows the harness distinguishes signed from unsigned order), `sanity_pu` (`M == M2` with no load guard: shows the power-up value of M really is free in the formal model, so the power-up proofs are not trivially true). Checker sanity only; not DUT mutation. | checker sanity |
| Structure / interface | Yosys on the unoptimised netlist (`proc -noopt; flatten`): `check -assert`, `scc` (combinational cells) asserted empty, no reset/async/latch/memory/negedge state types, then `opt_clean` and `lint/check_interface.py` on `write_json`: ports (R9), 22 flop bits, positive edge, clock = `clk` port, no reset types, no `init` attribute, no black boxes (R8, R11). Verilator `-Wall` lint classified by `lint/check_lint.py` (R10). | static |

### Assumptions and observer initialisation (formal)

There are **no assumptions** (`assume`, `restrict`, `anyconst`, `anyseq`) in the harness or the
`.sby`; `clk`, `first`, `en`, `S_in` are free at every step. The DUT has no initial value; the
`.sby` asserts that no wire outside the harness carries an `init` attribute, so the DUT's M is
free at step 0 (and `sanity_pu` demonstrates it). The only initialised registers are the
harness's observers (`pv`, `loaded`, `nacc`, `nhold`, `reloads`, `gap`), which start in
"nothing observed yet". They never drive the DUT, so they cannot restrict its behaviour; they
only define when a property applies (for example "after a load").

### Why these are unbounded proofs

`prove_*` is SBY k-induction: the basecase (BMC of depth 4 from the initial state, with M
free) and the induction step (any 4 consecutive states satisfying the assertions, from an
arbitrary state, are followed by a state satisfying them) both pass, which proves the
assertions in every reachable state at every time. The step and power-up invariants are
1-inductive by construction (the harness registers the reference decision, so each assertion
compares registers bit by bit). `pdr_*` is abc pdr (IC3), an independent unbounded engine,
which returns PASS only with an inductive invariant. Both engines agree on all three property
groups.

Single clock: without `multiclock`, SBY models every flop as updated at each step, whatever its
clock signal. This is sound for the contract because R11 (checked by `lint` and by a guard in
the `.sby` that rejects negative-edge, asynchronous, latch and memory cells) requires every flop
to be a positive-edge flop clocked by `clk`. The `.sby` script runs `hierarchy; proc`, then the
init guard (it must run before `flatten`, because afterwards every wire belongs to
`max_reg_props`), then `flatten; opt_clean` (which collapses non-inverting clock buffers), then
`prep` and the type/polarity guards. A clock that is still derived after that (inverted,
gated) is refused by SBY ("derived clocks are only supported with clk2fflogic"), which gives
`inconclusive`, so it fails closed.

## 5. Result labels (results.json)

Each item has `status` (the contract's own label), `label` (the standard AGENT_CONTEXT label),
`expected_outcome` and `ok`. `all_ok` is the conjunction of `ok`.

| status | label | meaning |
|---|---|---|
| `proven` | `proven` | unbounded formal proof (section 4) with the expected number of assertions in the model |
| `pass-sampled` | `pass-sampled` | directed or random simulation; not a proof |
| `pass-exhaustive-subspace` | `pass-sampled` | every input of the declared reduced subspace (`sim_onestep`); not exhaustive over the full input space |
| `covered` | `bounded-pass` (`depth: 10`) | every cover reached within depth 10; a witness, not a proof |
| `failed-as-expected` | `failed` (`expected_outcome: fail`, `ok: true`) | negative control refuted with a trace, the required outcome |
| `pass`, `pass-with-waiver` | `pass-static` | static or infrastructure check passed: lint, structure, interface, model self-test, build, cell extraction. Evidence, not a proof. `pass-with-waiver` (gate mode only): lint passed, with warnings only in the unmodified PDK cell models |
| `failed` | `failed` | check failed. Includes an engine that returned FAIL when SBY then could not replay its trace (abc pdr: "Could not determine aigsmt status", SBY status ERROR): the engine's counterexample verdict stands; the detail names the engine line |
| `not-proven` | `inconclusive` | k-induction did not close (SBY status UNKNOWN: basecase passed, induction step failed at depth 4). Not a proof, not a counterexample, not a tool error; `ok: false` |
| `timed-out` | `timed-out` | tool timeout (900 s formal and simulation, 600 s build) |
| `inconclusive` | `inconclusive` | tool or infrastructure error (an SBY traceback or error with no engine verdict, no PASS/FAIL status, or a job that recorded no result); no verdict; `ok: false` |

Each SBY task runs in its own directory with its own copy of `max_reg.sby`, so parallel tasks
never share SBY's status database.

## 6. Running on other designs, output location, gate level

- `run_all.sh` with no arguments runs the golden RTL and writes `results.json`,
  `run_all.console.log`, `logs/` and `formal/runs/` in this directory (the Phase 1 evidence).
  `--rtl FILE` requires `--out DIR`, and `DIR` may not be this directory, so a run on any other
  DUT never touches the Phase 1 evidence.
- `--gate` (with `--rtl NETLIST`) runs a gate-level netlist with top module `max_reg`.
  `gate/extract_cells.py` (the ripple_add approach) builds two views from the unchanged netlist:
  - **simulation view** `max_reg.v`: the netlist plus only the Verilog models it uses
    (transitively), from `--cells DIR` (default GF180 7-track `.../gf180mcu_fd_sc_mcu7t5v0/verilog/`),
    preprocessed with `FUNCTIONAL` **defined** and `USE_POWER_PINS` **undefined**, including the
    flop UDP (`udp_n_iq_ff`). Verilator 5.046 and Icarus both run UDPs.
  - **Yosys view** `max_reg_fv.v`: the same netlist and combinational models, but the cells that
    need a UDP (flops) are modelled from the PDK **liberty** `ff` group (`read_liberty
    -ignore_miss_func`, `--lib`, default TT 025C 3V30), because Yosys cannot read UDPs. Used by
    the structure check and SBY.

  So flop behaviour comes from two independent PDK views (Verilog UDP in simulation, liberty in
  formal); both must pass. Compared with the ripple_add script, the UDP-instance pattern was
  fixed: an unnamed UDP instance written without a space before `(` was not recognised there
  (harmless for ripple_add, which has no flops).
- Gate mode runs every item (no item depends on a parameter), plus **`eqy_rtl`**: EQY
  (`gate/eqy_rtl.eqy`, strategy `sat`, depth 1) of the Yosys view against the golden RTL. The
  state is matched by name (the 22 flops behind `M`), and each partition's next-state and
  output function is proven equal, so PASS is an unbounded equivalence proof (`proven`), in
  under 1 s. It adds an independent full-function check of the netlist against the golden RTL,
  with no harness. FAIL ("equivalence unknown") is labelled `failed`. A netlist that re-encodes
  the state so that no name match exists would fail it and would need its own reviewed match.
  Checked: PASS on the mapped golden netlist and on the mapped `>=` variant (equivalent), FAIL on
  the mapped unsigned-compare netlist (`review/gate_netlists/`, `review/gate_mutants/`). Lint: Verilator `-Wall` on the
  simulation view; warnings located after the end-of-netlist marker (the unmodified PDK models:
  `IMPLICIT`, `BLKSEQ`, `UNDRIVEN notifier`, `DECLFILENAME`) are listed and not counted (status
  `pass-with-waiver`); any warning in the netlist fails. The Verilator build uses `-Wno-fatal`
  in gate mode only, for the same PDK warnings.
- Evidence for the golden max_reg mapped to GF180 (`gate/synth_gf180.sh`, the `synth_area.py`
  recipe with `write_verilog -noattr`; `gate/netlists/max_reg_gf180.v`, 135 cells including 22
  `dffq_1`, 3,360.85 µm²): `gate/evidence/golden_gf180/`.

## 7. Future work: clock-gating extension (recorded from the Phase 1 review, N3)

R11 rejects clock gating today. This is justified, because the single-clock SBY model is unsound
for a gated clock, SBY refuses derived clocks, the liberty has no function for
`icgtp`/`icgtn`, and glitch-freedom and enable timing are STA properties. It is also necessary:
a hand-made latch+AND gate and ICG netlists pass every simulation item. Clock gating is a
realistic power optimisation here (an ICG enabled by `en` stops the clock on all 22 flops except
on the 1-in-1,024 `en` cycles). Allowing it needs a contract amendment with a new review, and
the amendment must add all of the following:

1. **Allow-list.** Only `gf180mcu_fd_sc_mcu7t5v0__icgtp_*`, with `CLK` = the `clk` net (after
   buffer collapse) and `TE` tied 0. Every flop clock must be either `clk` or such an ICG's `Q`,
   possibly through non-inverting clock buffers. No other logic on any clock net, so a hand-made
   AND/latch gate stays rejected.
2. **Validated ICG model.** A formal ICG model written from the datasheet (latch transparent
   while CLK is low, then AND), validated against the PDK Verilog UDP model by exhaustive
   simulation of its 3 inputs over both clock phases.
3. **Multiclock formal.** `multiclock on` (clk2fflogic) with `clk` as an explicit toggling input.
   The only new assumption allowed is that `clk` alternates. Rerun `a_step`, `a_seq` and `a_pu`.
   The ICG latch has no init, so it joins the power-up miter. Keep the negative controls and add
   one: an enable stuck at 0 must fail.
4. **Enable-sufficiency property.** At every rising edge where the RTL load condition holds, the
   gated clock pulses. This is implied by (3), but it is stated as its own assertion for diagnosis.
5. **Extension mutants.** Enable stuck at 0 and at 1, enable missing `first`, enable = `S_in > M`
   only, a hand-made AND gate, an ICG on an inverted clock, `TE` floating.
6. **Signoff.** STA clock-gating setup/hold checks on the ICG enable, enabled in the Phase 4 flow.

## 8. X (4-state) behaviour

X/Z inputs are not specified. M has no reset, so before the first load it is X in Icarus and a
random 2-state value in Verilator (`--x-initial unique`) and in formal (free).

| Check | Value semantics | Sees an X on M after a load? |
|---|---|---|
| SBY formal | 2-state; undriven nets become free values; an X constant becomes some 2-state value | usually, as a counterexample (an X that happens to resolve to the right value is not seen) |
| Icarus (`vec`) | 4-state; compares with `!==` on every cycle where the model knows M | yes, for the stimulus applied |
| Verilator (`vec`, `sim_*`) | 2-state | no |

So Verilator passes are 2-state evidence; X-freedom of M after a load rests on Icarus (for the
vectors applied) and, in practice, on formal.
