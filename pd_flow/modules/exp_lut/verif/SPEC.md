# exp_lut: verification specification

Design under test: `pd_flow/modules/exp_lut/snapshot/exp_lut.v` (immutable golden, SHA-256
`873546cc…`, identical to `pd_flow/baseline/original_rtl/exp_lut.v`; never edited). Any later
implementation is checked against this same contract with `run_all.sh --rtl FILE --out DIR`
(both REGISTERED values); a gate-level netlist of one configuration with
`run_all.sh --gate --rtl NETLIST [--registered N] --out DIR` (section 6).
Sources used to derive the requirements: the RTL header and body, the instance in
`snapshot/attention_controller.sv` (line 109) and its FSM, `mac_unit.v` (how `D` and `W` are
produced and consumed), `python/src/attention_model.py` (`exp_weight`, `exp_table`),
`test/blocks/test_exp_lut.py`, and `PHASE0_AUDIT.md` invariant 3. The structure follows the
approved `max_reg` contract, including its review amendments (N1 clock-buffer flatten,
N2 labels, gate-mode `eqy_rtl`).

## 1. Function

`exp_lut` turns a score difference into a softmax weight:

    D' = round_half_up(D / 2^shift) = floor(D / 2^shift + 1/2)      D unsigned 22-bit, shift 0..15
    W  = round(255 · e^(−D'/4))                                     8-bit unsigned

`W` is 0 for every `D' >= 25` (because `255·e^(−25/4) = 0.493 < 1/2` and `e^x` is monotone), so
only 25 non-zero values exist (255, 199, 155, 120, 94, 73, 57, 44, 35, 27, 21, 16, 13, 10, 8, 6,
5, 4, 3, 2, 2, 1, 1, 1, 1 for D' = 0..24). Call this function `f(D, shift)`.

`REGISTERED` (parameter, default 1) selects the timing:

| REGISTERED | done | W | Latency | State |
|---|---|---|---|---|
| 0 (shipped) | `start` (combinational) | `f(D, shift)`, combinational | 0 | none |
| 1 (block test) | `start` delayed one clock; synchronous active-low reset clears it | loads `f(D, shift)` at a rising edge with `start`, holds otherwise; reset clears it to 0 | 1 clock | 9 flops, no initial value |

The barrel shifter, guard bit, out-of-range logic and the case table are implementation
choices and are **not** part of the contract; only `f` and the port timing are.

### Where the RTL is the specification (not mathematics)

The golden model (`model/golden_model.py`) computes `f` from the definition with exact rationals
and `e^x` (double and 60-digit decimal, which must agree). The following choices come from the
RTL and its header, not from mathematics, and the contract takes them as given:

| # | Choice | Source |
|---|---|---|
| S1 | Scale 255, 4 D' units per nat, 8-bit unsigned W | RTL header formula, port width |
| S2 | D' rounds **half up** (a tie `D mod 2^shift = 2^(shift−1)` goes up); shift = 0 does not round (`floor(D + 1/2) = D`, so not a special case) | RTL header ("add 2^(shift−1), then shift"); `exp_weight(score_round=True)` |
| S3 | D is **unsigned** 22-bit: `D[21] = 1` (a negative two's-complement score on the controller's `score` bus) is a large D and gives W = 0 | RTL (`diff = D`, `|diff[21:20]` → out of range); `exp_weight` checks D unsigned |
| S4 | W = 0 for D' >= 25 (the 26th and later entries) | follows from the math; also the RTL's `default` |
| S5 | REGISTERED = 1 handshake: synchronous reset clears `done` and `W`; `done` = `start` one clock later; W loads only on `start` and holds otherwise; reset wins over `start` | RTL body and header ("Handshake") |
| S6 | REGISTERED = 0: `done = start`, W follows D and shift | RTL header |
| S7 | Rounding of W: no tie exists (`255·e^(−k/4)` is irrational for k >= 1, and the nearest half-integer is at least 0.0077 away for k = 0..63), so the tie rule of the outer `round` is irrelevant | model selftest |

The model never reads the RTL table. It is cross-checked against the project's own model
`exp_weight()` in `python/src/attention_model.py` (which the RTL says it must match) on 33,251
points (every interval boundary ±1 and 2,000 random D per shift, D <= 2,088,960): no mismatch.

## 2. Use in the design

```
exp_lut #(.REGISTERED(0)) exponent_unit (
    .clk(clk), .rst_n(rst_n), .start(1'b0), .D(score), .shift(score_shift),
    .done(exp_done), .W(weight));
```

| Signal | Driven by | What the controller relies on |
|---|---|---|
| `D` | `score` (mac_unit `S`, signed 22-bit). In pass 2 the score register is preloaded with M and subtracts, so after the score row `S = M − S_t = D >= 0` | `W` is consumed only while `accum_mode`/VALUE (mac_unit `W` input), after the score row of pass 2, so the consumed `D` is in `[0, M − S]` ⊆ `[0, 2,088,960]` (INT8: 1,048,576 − (−1,040,384)), i.e. `D < 2^21`. At other times `score` holds partial or pass-1 sums, possibly negative; W is then not used. |
| `shift` | `score_shift` input, host configuration, held from start until idle | all 16 values |
| `start` | tied 0 | `done` (`exp_done`) unused |
| `clk`, `rst_n` | chip clock and reset | unused at REGISTERED = 0 |
| `W` | to mac_unit `W` (weight × V into the ring and into `L`) | `W = f(D, shift)` combinationally, in the same cycle, while D and shift are stable |

The controller relies on R1 to R7 and R17. The contract checks the **full** 22-bit D range and
every shift, not only the consumed range, because the module's own behaviour is specified there
(S3). `D >= 2^21` (D[21] = 1) is a don't-care of the chip; exploiting it (for example ignoring
`D[21]`) is **not** allowed by this contract and would need a reviewed amendment that restricts
R4 to `D < 2^21` with a proof of the controller-side invariant. `fv_sanity_d21_r0` shows that the
contract rejects such a design.

## 3. Requirements

`f` is defined in section 1. "Edge" means a rising edge of `clk`.

| ID | Requirement |
|---|---|
| R1 | **Function.** For every D in [0, 2^22) and every shift in 0..15 (2^26 pairs), the weight is `f(D, shift)` (REGISTERED = 0: W at all times; REGISTERED = 1: W after a load edge). |
| R2 | **Rounding of D'.** D' = floor(D / 2^shift + 1/2): ties go up (S2), shift = 0 uses D itself. Covered by R1; stated separately because truncation (`D >> shift`) is the likely alternative and must fail. |
| R3 | **Table and zero region.** W > 0 exactly when D' <= 24; W = 0 for every D' >= 25; for fixed shift, W is non-increasing in D. (Consequence of R1.) |
| R4 | **Out-of-range D.** W = 0 for every D >= 2^20 at every shift (largest non-zero D: 802,815 at shift 15), including every D with D[21] = 1 (S3). |
| R5 | **Output.** W is 8-bit unsigned, 0..255, with no X or Z for known inputs (REGISTERED = 1: after the first reset or load). |
| R6 | **REGISTERED = 0 timing.** W = f(D, shift) combinationally, at every time, whatever `clk`, `rst_n` and `start` are (they must not affect W); zero latency; no state. |
| R7 | **REGISTERED = 0 done.** `done == start` at every time. |
| R8 | **REGISTERED = 1 reset.** At an edge with `rst_n = 0`, `done` becomes 0 and W becomes 0, whatever `start`, D and shift are (synchronous, reset wins over start). |
| R9 | **REGISTERED = 1 load.** At an edge with `rst_n = 1, start = 1`, W becomes `f(D, shift)` of the values at that edge; latency one clock. |
| R10 | **REGISTERED = 1 hold.** At an edge with `rst_n = 1, start = 0`, W is unchanged, whatever D and shift are. W changes only at edges: no combinational path from any input to W or `done`, no change at the falling edge. |
| R11 | **REGISTERED = 1 sequence.** After a reset, W equals `f` of the inputs at the most recent load edge since that reset, or 0 if there was none. (Follows from R8 to R10.) |
| R12 | **REGISTERED = 1 done.** At every edge, `done` becomes `rst_n && start`: high for exactly one cycle after a one-cycle start pulse, high in consecutive cycles for back-to-back starts, registered (R10). |
| R13 | **Power-up (REGISTERED = 1).** The 9 state bits have no initial value. Before the first edge `done` is unspecified; before the first reset or load W is unspecified. R8 to R10 and R12 hold from power-up for **any** state, so all behaviour from the first reset or load on is independent of the power-up state. |
| R14 | **Interface.** Exactly the ports `clk` (in, 1), `rst_n` (in, 1), `start` (in, 1), `D` (in [21:0]), `shift` (in [3:0]), `done` (out, 1), `W` (out [7:0]); one parameter `REGISTERED`, **default 1** (the block test instantiates the module without a parameter, the controller with 0). Names, directions and widths must not change (the controller connects by name). |
| R15 | **Structure.** REGISTERED = 0: no state element at all. REGISTERED = 1: exactly 9 flop bits; every flop is a positive-edge D flop without asynchronous reset or set (the synchronous reset is logic in front of D), clocked by the `clk` port, where "clocked by `clk`" means after collapsing non-inverting buffers (`flatten; opt_clean`, as both the lint structure check and the `.sby` do), so a CTS clock buffer is accepted and an inverted, gated or derived clock is not. Both: no latches, memories or `$anyinit`; no `init` attribute on any wire; no combinational loops, undriven or multiply-driven nets; no black boxes. As for max_reg this is also a **contract assumption** of the single-clock formal model (section 4); clock gating needs a reviewed extension (max_reg SPEC §7 lists what it must contain). |
| R16 | **Lint.** RTL: `verilator --lint-only -Wall` gives no warning and no error at both REGISTERED values (no waivers). Gate level: no warning located in the netlist, except the port waiver of section 6 (REGISTERED = 0 netlist: unused `clk`, `rst_n`). |
| R17 | **Controller use.** With REGISTERED = 0, `start = 0` and D, shift stable, W = f(D, shift) for every D in [0, 2,088,960] and every shift, and `done = 0`. (Follows from R1, R6, R7; it is the subset the chip consumes.) |
| R18 | **Agreement with the project model.** `f` equals `exp_weight(M, S, score_shift, score_round=True)` of `python/src/attention_model.py` wherever that model accepts D. (Checked in `selftest`; it is a consistency check of the reference, not of the DUT.) |

Out of scope: timing, area and power (Phase 2+ metrics); X/Z **inputs** (not specified);
multi-clock behaviour; clock gating; `D` values the controller never consumes are **in** scope (S3).

## 4. Verification approach

| Method | What | Strength |
|---|---|---|
| Golden model | `model/golden_model.py`: D' with `Fraction` (`floor(D/2^s + 1/2)`), W with `math.exp` and 60-digit `Decimal` (must agree), zero region by the monotone bound. `selftest`: 10 hand-derived W KATs (255/e = 93.81 → 94, …), 13 D' KATs, ties at every shift, tie margin, a second integer formulation of D' (`(2D + 2^s) // 2^(s+1)`) on 4,096 + 20,000 D per shift, thresholds vs D', interval consistency, and R18. Emits `intervals` (352 maximal constant runs `shift lo hi W`, covering every D for every shift), `vhdr` (`ref_wtab(k)`, `ref_thr(s, k)` for the formal harness) and `vectors`. | reference |
| Exhaustive, Verilator | `sim_exh_r0`: all 2^26 (D, shift) with `clk`, `rst_n`, `start` pseudo-random at every point: W against **two** references (interval file; the TB's own double-precision formula `floor(255·exp(−floor(D/2^s + 0.5)/4) + 0.5)`), `done == start` (R1 to R7). `sim_exh_r1`: all 2^26 pairs loaded with `start` (W, `done` after the edge), each followed by a hold cycle with other random D, shift (W holds, `done = 0`), a reset with `start = 1` every 4,096 loads, the no-comb-path and falling-edge checks on every one of 134 M cycles, plus the next-state rule from the observed outputs (R1 to R5, R8 to R12). | exhaustive |
| Exhaustive, Icarus (4-state) | `ivl_exh_r{0,1}_s{a}_{b}`: the same 2^26 pairs, split into four items by shift range (0..3, 4..7, 8..11, 12..15) so they run in parallel; together they cover the whole space. Compares with `!==`, so X/Z on W or done fails. REGISTERED = 0: `clk`, `rst_n`, `start` vary at each point. REGISTERED = 1: back-to-back loads (each checked), a hold cycle with other inputs after every 16th load, a reset before each shift and every 4,096 loads, no-comb-path and falling-edge checks. | exhaustive |
| Sequential random (REGISTERED = 1) | `sim_seq_r1`: 100 M cycles, regimes of 20 to 2,000 cycles with P(start) in {0, 0.1, 0.5, 0.9, 1} and P(reset) in {0, 0.01, 0.2}, D near interval boundaries, small, in the consumed range or full 22-bit; next-state rule from the observed outputs on every cycle from a random power-up state, and a shadow reference after the first reset (R8 to R13). `vec_r1`: 206,052 golden-model vector cycles (directed: start before any reset, reset with start, every D' 0..33 at every shift at/below/above each threshold, holds with changing inputs; then random regimes) on Verilator and Icarus. `sim_powerup_r1`: 64 random power-up states (62 distinct), identical traces from the first reset on (R13). | sampled |
| Formal REGISTERED = 0 | `fv_equiv_r0` (smtbmc/Z3) and `fv_pdr_equiv_r0` (abc pdr): `a_wA: W == wA`, `a_wB: W == wB`, `a_done: done == start` for every input (clk, rst_n, start, D, shift free). The design has no state, so this is a **complete combinational equivalence** against two independent formal references: wA computes D' by 23-bit add-and-shift and looks up `ref_wtab`; wB counts the thresholds `ref_thr(shift, k)`, k = 1..25, that D reaches (no shift, no add). Neither uses the RTL's guard bit, staged shifter or out-of-range terms; the only shared data is the generated include, which the model computes from the definition. | proven |
| Formal REGISTERED = 1 | `fv_prove_r1` (k-induction, depth 4) and `fv_pdr_r1` (abc pdr): `a_step_W` (W == `!rst_n ? 0 : start ? wA : W` of the previous step, from the **observed** state), `a_step_done` (`done == rst_n && start` of the previous step), the decomposed `a_rst`, `a_load`, `a_hold` (R8, R9, R10, R12), and `a_seq` (after a reset, W == shadow register loaded with formulation **wB**, R11). DUT state free at step 0 and, in the induction step, everywhere. | proven |
| Covers | `fv_cover_r0` (depth 1, 47 covers): every D' 0..25 with its W, a rounding tie rounded up at every shift 1..15 with non-zero W, D in [2^20, 2^21) and D[21] at shift 15 giving 0, the last non-zero (D = 802,815) and first zero (802,816) at shift 15, done with start high and low. `fv_cover_r1` (depth 10, 10 covers): non-zero power-up W, a load before any reset, a load changing W, a load giving 0, a hold while the inputs would give another W, 3 holds after a load, reset winning over start, back-to-back loads, the done pulse falling, W = 255 after a reset. Every cover must be reached; `run_all.sh` checks the counts. | bounded-pass |
| Negative controls | Must be **refuted** with a trace: `sanity_trunc_r0` (reference truncates D'), `sanity_d21_r0` (reference ignores D[21]), `sanity_pu_r1` (W == 0 at power-up: shows the DUT state is free), `sanity_lat0_r1` (zero-latency reference). Checker sanity only; DUT mutation is Agent 2's task. | checker sanity |
| Structure / interface | Yosys on the unoptimised netlist (`proc -noopt -norom; flatten`) per configuration (`chparam`): `check -assert`, `scc` asserted empty, no reset/async/latch/memory/negedge state types, then `opt_clean` and `lint/check_interface.py` on `write_json`: ports (R14), 0 or 9 flop bits, polarity, clock net = `clk`, no `init` attribute, no black boxes (R15). RTL mode also elaborates the default parameter and requires the REGISTERED = 1 structure (default = 1, R14). Verilator `-Wall` classified by `lint/check_lint.py` (R16). | static |

### Assumptions and observer initialisation (formal)

There are **no assumptions** (`assume`, `restrict`, `anyconst`, `anyseq`) in the harness or the
`.sby`; `clk`, `rst_n`, `start`, `D`, `shift` are free at every step. The DUT has no initial
value; the `.sby` asserts that no wire outside the harness carries an `init` attribute (the
guard runs after `proc` and **before** `flatten`, the max_reg N1 lesson), so the DUT's state is
free at step 0 (and `sanity_pu_r1` demonstrates it). The only initialised registers are the
harness observers (`pv`, `seen`, and for covers `pdone`, `nhold`, `ppl`), which start in "nothing
observed yet". They never drive the DUT; they only define when a property applies. The
reference registers `eW`, `eD`, `pW`, `pwA`, `prst`, `pst`, `sW` have no initial value and are
read only once `pv` (or `seen`) guarantees they were written.

### Why these are unbounded proofs

REGISTERED = 0: there is no state element (also checked by R15), so the asserted relation is a
pure function of the current inputs; a pass at any depth >= 1 covers every input, and both
engines (Z3 and abc pdr) report PASS. REGISTERED = 1: `prove_r1` is SBY k-induction (basecase
BMC of depth 4 from a free state, and the induction step from an arbitrary state); the
step assertions compare registered references bit by bit, so they are 1-inductive by
construction. `pdr_r1` is abc pdr (IC3), an independent unbounded engine. Both agree.

Single clock: without `multiclock`, SBY models every flop as updated at each step. This is sound
because R15 (checked by `lint` and by guards in the `.sby` that reject negative-edge,
asynchronous, latch and memory cells) requires every flop to be a positive-edge flop clocked by
`clk`. The `.sby` runs `hierarchy; proc -norom`, the init guard, `flatten; opt_clean` (which
collapses non-inverting clock buffers), `prep` and the type/polarity guards. A clock that is
still derived after that is refused by SBY, which gives `inconclusive`: it fails closed.
`proc -norom` keeps case tables as logic, so the `$mem` guard stays strict.

## 5. Result labels (results.json)

Each item has `status` (the contract's own label), `label` (the standard AGENT_CONTEXT label),
`expected_outcome` and `ok`. `all_ok` is the conjunction of `ok`.

| status | label | meaning |
|---|---|---|
| `proven` | `proven` | unbounded formal proof (section 4) with the expected number of assertions in the model, or an EQY PASS (`eqy_rtl`) |
| `pass-exhaustive` | `pass-exhaustive` | simulation of every input pair of the declared space (`sim_exh_*`: all 2^26; `ivl_exh_*`: all D for the shifts named in the detail, the four items together all 2^26) |
| `pass-sampled` | `pass-sampled` | directed or random simulation; not a proof |
| `covered` | `bounded-pass` (`depth: 1` or `10`) | every cover reached within the depth; a witness, not a proof |
| `failed-as-expected` | `failed` (`expected_outcome: fail`, `ok: true`) | negative control refuted with a trace, the required outcome |
| `pass`, `pass-with-waiver` | `pass-static` | static or infrastructure check passed: lint, structure, interface, model self-test, model data generation, build, cell extraction. Evidence, not a proof. `pass-with-waiver` (gate mode only): lint passed, with warnings only in the unmodified PDK cell models or covered by the REGISTERED = 0 port waiver |
| `failed` | `failed` | check failed. Includes an engine that returned FAIL when SBY then could not replay its trace (abc pdr: "Could not determine aigsmt status", SBY status ERROR): the engine's verdict stands; the detail names the engine line |
| `not-proven` | `inconclusive` | k-induction did not close (SBY status UNKNOWN: basecase passed, induction step failed at depth 4). Not a proof, not a counterexample, not a tool error; `ok: false` |
| `timed-out` | `timed-out` | tool timeout (900 s formal and simulation, 600 s build) |
| `inconclusive` | `inconclusive` | tool or infrastructure error (an SBY traceback or error with no engine verdict, no PASS/FAIL status, or a job that recorded no result); `ok: false` |

Each SBY task runs in its own directory with its own copy of `exp_lut.sby`.

## 6. Running on other designs, output location, gate level

- `run_all.sh` with no arguments runs the golden RTL at both REGISTERED values and writes
  `results.json`, `run_all.console.log`, `logs/` and `formal/runs/` in this directory (the
  Phase 1 evidence; `logs/` and `formal/runs/` are git-ignored). `--rtl FILE` requires
  `--out DIR`, and `DIR` may not be this directory. `--jobs J` (default 3, at most 8).
- An RTL candidate must keep the `REGISTERED` parameter (R14); both configurations are run
  (items suffixed `_r0`, `_r1`).
- `--gate --rtl NETLIST [--registered N]` runs a gate-level netlist (top module `exp_lut`, no
  parameter) of **one** configuration, `N` = 0 (default, shipped) or 1. Only that
  configuration's items run. `gate/extract_cells.py` (the fixed max_reg version, unchanged)
  builds two views from the unchanged netlist: the **simulation view** `exp_lut.v` (netlist plus
  only the Verilog models it uses, `FUNCTIONAL` defined, `USE_POWER_PINS` undefined, including
  the flop UDP) for Verilator and Icarus, and the **Yosys view** `exp_lut_fv.v` (the same netlist
  and combinational models, flops from the PDK liberty `ff` group) for the structure check, SBY
  and EQY. Flop behaviour therefore comes from two independent PDK views; both must pass.
- Gate mode adds **`eqy_rtl`**: EQY (`gate/eqy_rtl.eqy`, strategy `sat`, depth 1) of the Yosys
  view against the golden RTL with `chparam REGISTERED N` (`proc -norom` on both sides: the
  sat strategy skips any partition that contains a memory, and the golden's case table would
  otherwise become a ROM; without it the item ends `inconclusive`). For N = 0 there is no state, so PASS
  is a complete combinational equivalence; for N = 1 the 9 state bits are matched by name (they
  drive `W` and `done` directly) and PASS is an unbounded equivalence proof. Labelled `proven`;
  FAIL is `failed`. A netlist that re-encodes the state would fail it and need its own reviewed
  match. `eqy_rtl` cannot see clock polarity (max_reg finding), which lint, the `.sby` guards
  and simulation check.
- Gate lint: Verilator `-Wall` on the simulation view. Warnings after the end-of-netlist marker
  (the unmodified PDK models: `IMPLICIT`, `BLKSEQ`, `UNDRIVEN notifier`) and `DECLFILENAME` are
  listed and not counted. **Port waiver**, REGISTERED = 0 netlists only: `UNUSEDSIGNAL` on
  exactly `clk` and `rst_n`. Such a netlist has no state, so these required ports (R14) are
  unconnected; the RTL suppresses the same warning with its `_unused` wire, which synthesis
  removes. Any other netlist warning fails. Status `pass-with-waiver`. The Verilator build uses
  `-Wno-fatal` in gate mode only, for the PDK warnings.
- Netlists for the golden: `gate/synth_gf180.sh <out.v> <REGISTERED> [rtl.v]` (the max_reg /
  `synth_area.py` recipe plus `chparam`): `gate/netlists/exp_lut_r0_gf180.v` (102 cells,
  2,414.72 µm², matches PHASE0_AUDIT) and `gate/netlists/exp_lut_r1_gf180.v` (113 cells including
  9 `dffq_1`, 2,996.45 µm²). Evidence: `gate/evidence/golden_r0_gf180/`, `gate/evidence/golden_r1_gf180/`,
  and `gate/evidence/clkbuf_r1/` (the r1 netlist with one `clkbuf_1` from `clk` to all flops,
  as CTS produces: must pass).

## 7. X (4-state) behaviour

X/Z inputs are not specified. REGISTERED = 1 state has no reset value until the first reset: it
is X in Icarus and a random 2-state value in Verilator (`--x-initial unique`) and in formal
(free).

| Check | Value semantics | Sees an X on W or done? |
|---|---|---|
| SBY formal | 2-state; undriven nets become free values | usually, as a counterexample |
| Icarus (`ivl_exh_*`, `vec_r1`) | 4-state, `!==` on every checked value | yes, over the full input space |
| Verilator (`sim_*`, `vec_r1`) | 2-state | no |

So X-freedom of W and done for known inputs rests on the Icarus exhaustive items (REGISTERED = 1:
after the first reset or load).
