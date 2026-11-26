# divider: verification specification

Design under test: `pd_flow/modules/divider/snapshot/divider.v` (immutable golden, SHA-256
`a4943458…`, equal to `pd_flow/baseline/original_rtl/divider.v`; never edited). Any later
implementation is checked against this contract with `run_all.sh --rtl FILE --out DIR` (both
configurations), and a gate-level netlist of one configuration with
`run_all.sh --gate --rtl NETLIST [--config CC] --out DIR` (section 6).

Sources used for the requirements:
- the RTL header and body;
- the instance in `snapshot/attention_controller.sv` (line 113) and the controller FSM;
- `python/src/attention_model.py` (`divide_round`, `reg_widths`);
- `test/divider/` and `PHASE0_AUDIT.md`.

The structure follows the approved `exp_lut` and `max_reg` contracts, including their review
lessons:
- the init guard runs before `flatten`;
- clock buffers are flattened;
- `not-proven` is kept distinct from `failed`;
- gate-mode `eqy_rtl`;
- no check's exit status is taken through a pipe (exp_lut B1).

Under **user decisions D9/D9b**:
- **sequential behaviour** is proven with SBY;
- **the arithmetic** is proven with SBY at the golden (white-box lemmas, section 4) and is checked
  by directed edge cases plus fixed-seed spot checks;
- **EQY against the golden** is the mandatory gate for any candidate;
- there is **no exhaustive simulation**.

Configurations: **00** = `LATCH_DENOMINATOR = 0, CHECK_INVALID = 0` (the shipped one, used by the
controller). **11** = `1, 1` (the defaults, used standalone and by `test/divider`).

## 1. Function

For a request with operands S = `sum_in` (signed 20-bit) and L = `denominator` (unsigned 12-bit):

    m      = floor(16·|S|/L + 1/2) = floor((32·|S| + L) / (2·L))      (round half up on |x|)
    result = sign(S) · m          i.e. round(16·S/L), nearest, ties AWAY from zero
    valid  = L != 0  and  S != −2^19  and  (S >= 0 ? m <= 2047 : m <= 2048)

The result is a 12-bit two's complement code (INT8 plus 4 fractional bits), −2048..2047.

### Where the RTL is the specification (not mathematics)

| # | Choice | Source |
|---|---|---|
| S1 | Scale 16 (4 fractional bits), 12-bit signed result | RTL header, `divide_round(out_frac=4)` |
| S2 | Ties go **away from zero** for both signs (−x.5 → −(x+1)) | RTL header; `divide_round` (rounds the magnitude, then negates) |
| S3 | Invalid: L = 0, S = −524288, or rounded value outside −2048..2047. At CHECK_INVALID = 1 the result is **0** at the normal latency (not saturation) | RTL header and `invalid`/`overflow` logic |
| S4 | Latency 24 edges after the accept edge (23 division steps + 1 round/sign step); data-independent | RTL header and FSM |
| S5 | `done` pulses one cycle; `busy` = not idle | RTL |
| S6 | `shift` shifts `result` left by one, taking in 0, in every state (serial output MSB first on `result[11]`); a completing division overrides a shift in the same cycle | RTL header and body |
| S7 | Synchronous active-low reset: idle, `done` = 0, `result` = 0; aborts a division | RTL |
| S8 | `sum_in` is sampled only at the accept edge (both configurations). LATCH_DENOMINATOR = 1: `denominator` is sampled at the accept edge. LATCH_DENOMINATOR = 0: it is used live and must be stable (A1) | RTL header ("Integration contract") |

The golden model (`model/golden_model.py`) computes the result with exact integers from the
first formula. Its self-test checks it against a second formulation (`fractions.Fraction`,
rounding half away from zero by definition). It is also checked against the project's
`divide_round()`, which the RTL says it must match, on 30,732 points (R19). It never reads the RTL.

## 2. Use in the design and the caller's guarantees (configuration 00)

```
divider #(.LATCH_DENOMINATOR(0), .CHECK_INVALID(0)) divider_unit (
    .clk(clk), .rst_n(rst_n), .start(state == DIV_START && pos[P-1:0] == output_index),
    .sum_in(o0), .denominator(weight_sum), .shift(out_shift && out_valid),
    .busy(div_busy), .done(div_done), .result(result));
```

At configuration 00 the result written at a completion is specified **only for requests that
satisfy the caller's guarantees A1–A4**. Outside them the value written is a don't care (R17).
The guarantees are **assumptions of this module contract, which the controller-level contract
must later discharge**:

| # | Guarantee (per request) | Why the controller should satisfy it (to be proven at controller level) |
|---|---|---|
| A1 | `denominator` has the same value at every rising edge from the accept edge to the completion edge inclusive (25 edges). That value is the divisor L | `weight_sum` (mac_unit `L`) changes only while `accum_en` (state VALUE). The divider runs in DIV_START/DIV_WAIT, and the next request comes after OUTPUT |
| A2 | L >= 1 | L = Σ W over the tokens, and the maximum token has D = 0, so W = 255; hence L >= 255 (RTL header) |
| A3 | S != −524288 at the accept edge | \|O\| <= 16·255·128 = 522,240 < 2^19 (`reg_widths`) |
| A4 | the rounded value is in range: m <= 2047 for S >= 0, m <= 2048 for S < 0 | O/L is a weighted average of INT8 V, so 16·O/L ∈ [−2048, 2032] |

A1 is stricter than what the golden needs: the golden reads the denominator only at the 24
edges after the accept edge. The stricter form lets an implementation sample it at any of the
25 edges. The controller never shifts or starts while the divider is busy, but the contract does
not need that: shift and start are specified in every state.

## 3. Requirements

"Edge" means a rising edge of `clk`. The **accept edge** of a request is an edge with
`rst_n = 1`, `start = 1` and `busy = 0`. Its **completion edge** is the 24th edge after it,
unless a reset edge comes first.

| ID | Requirement |
|---|---|
| R1 | **Function.** At a completion edge, `result` becomes the value of section 1 for the S and L of the request: S = `sum_in` at the accept edge. For L: configuration 11 takes `denominator` at the accept edge; configuration 00 takes the stable value of A1. Configuration 11: for every S, L (invalid → R12). Configuration 00: for requests satisfying A1–A4 (R17). |
| R2 | **Rounding.** Nearest, with ties (16·\|S\|/L = k + 1/2) away from zero for both signs. Stated separately because truncation, ties toward zero and ties toward +∞ are the likely alternatives, and each must fail. |
| R3 | **Range and validity.** The valid set is exactly that of section 1. Every valid value −2048..2047 is producible: 2047 and −2048 are reached; 2048 and −2049 are invalid. |
| R4 | **Latency.** The completion edge is exactly the 24th edge after the accept edge, whatever the data. A new request can be accepted at the edge right after the completion edge, i.e. in the `done` cycle. |
| R5 | **busy/done.** `busy` is 1 exactly in the cycles after the accept edge up to and including the cycle before the completion edge (24 cycles), and 0 otherwise. `done` is 1 exactly in the one cycle after a completion edge. `busy` is 0 when `done` is 1. Both are registered. |
| R6 | **Starts while busy are ignored.** A `start` at an edge with `busy = 1` changes nothing: not the latency, not the operands, not the result. |
| R7 | **Operand sampling.** `sum_in` matters only at the accept edge (both configurations). Configuration 11: `denominator` matters only at the accept edge. Configuration 00: A1. |
| R8 | **Hold.** `result` changes only at a reset edge, a shift edge or a completion edge. Otherwise it holds, whatever the other inputs are. No combinational path from any input to `result`, `busy` or `done`. |
| R9 | **Shift.** At an edge with `rst_n = 1`, `shift = 1` and no completion, `result` becomes `{result[10:0], 0}`, whether idle or busy. Twelve shifts output the result MSB first on `result[11]` and leave 0. `busy` and `done` are not affected. |
| R10 | **Completion overrides shift.** At a completion edge with `shift = 1`, `result` becomes the new value (R1/R12), not the shifted one. |
| R11 | **Reset.** At an edge with `rst_n = 0` (synchronous, active low): `busy` → 0, `done` → 0, `result` → 0, whatever `start`, `shift` and the data are. A division in progress is aborted: no `done`, no result. |
| R12 | **Invalid requests (CHECK_INVALID = 1).** A request with L = 0, S = −524288 or an out-of-range value completes at the normal latency with `result` = 0 and a `done` pulse. This is not saturation. |
| R13 | **Power-up.** The state has no initial value. Before the first reset, all outputs are unspecified (the DUT may even look busy). From the first reset edge on, R1–R12 and R17 hold whatever the power-up state was. |
| R14 | **Interface.** The ports are exactly `clk`, `rst_n`, `start`, `shift` (in, 1), `sum_in` (in [19:0], signed), `denominator` (in [11:0]), `busy`, `done` (out, 1) and `result` (out [11:0], signed). There are exactly two parameters, `LATCH_DENOMINATOR` and `CHECK_INVALID`, both **default 1** (`test/divider` instantiates without parameters; the controller passes 0/0). Names, directions and widths must not change. |
| R15 | **Structure.** Every flop is a positive-edge D flop clocked by the `clk` port, without asynchronous reset or set; the synchronous reset is logic. "Clocked by `clk`" is judged after collapsing non-inverting buffers (`flatten; opt_clean`), so a CTS clock buffer passes. No latches, memories, `$anyinit` or `init` attributes. No combinational loops, undriven or multiply-driven nets, or black boxes. The **number** of flops is an implementation choice: it is reported, not constrained. Golden: 56 bits at 00, 69 at 11. |
| R16 | **Lint.** Verilator `-Wall` gives no warning other than UNUSEDSIGNAL on a non-port signal (dangling internal bits; the golden has one, `difference[12]`). In gate mode, warnings inside the PDK models are not counted. |
| R17 | **Configuration 00 domain.** At 00 the value written at a completion is specified only when A1–A4 hold for that request. Everything else (R4–R11, R13) is specified for all inputs, including requests outside the domain. A completion outside the domain still comes at the R4 latency with a `done` pulse; only its value is a don't care. |
| R18 | **Controller use.** At 00, under A1–A4: R1–R11 (a subset). |
| R19 | **Agreement with the project model.** Inside its domain, the golden model equals `divide_round(O, L)` of `python/src/attention_model.py`. Outside it, `divide_round` raises an assertion and the model returns "outside the domain". This is checked in `selftest`; it checks the reference, not the DUT. |

Out of scope: timing, area and power; X/Z inputs; multi-clock behaviour; clock gating (it would
need the reviewed extension described in max_reg SPEC §7).

## 4. Verification approach

| Method | Item(s) | What | Evidence kind |
|---|---|---|---|
| Golden model | `selftest`, `gen` | **`selftest`** checks the model `model/golden_model.py` (exact integers) four ways: 31 hand-derived KATs (ties ±0.5, ±1.5, range edges 2047/−2048 and 2048/−2049, S = 127·255 and −128·255, L = 0, S = −2^19); a second formulation with `Fraction` (78,665 points: every L with 7 numerators each, plus 50,000 random); 1,758 exact ties; and R19 (30,732 points against `divide_round`). **`gen`** writes `edges.txt` (7,353 points), listed below. | model (static) |
| Reference check | `refcheck` | The formal reference `formal/ref_divider_seq.v` (Icarus, `sim/tb_ref.sv`) is checked against the model on every `edges.txt` point: the value at 11, and the value and validity at 00. 0 mismatches are required. This ties the formal reference to the exact-integer definition. | edge/spot (reference) |
| Edge cases + spot checks | `edge_00`, `edge_11` | Every `edges.txt` point runs through the DUT (`sim/tb_edge.sv`, Icarus 4-state, `!==`); details below the table. About 2 s each for RTL and 30 s for gate level. | edge/spot (sampled) |
| Formal, black box | `fv_proto_00/11` (k-induction, depth 28), `fv_pdr_proto_00/11` (abc pdr) | Assertions `a_busy` (R4, R5, R6), `a_done` (R5), `a_rst` (R11), `a_shift` (R9), `a_hold` (R8) and `a_cnt` (harness), checked against a reference counter `cnt` (accept when `cnt` = 0 and `start`; completion at `cnt` = 24; starts while `cnt` != 0 ignored). Everything is asserted from the first reset edge with the DUT's power-up state free (R13). Depth 28 is more than one 25-edge division, so the induction closes without internal knowledge. Valid for **any** DUT, including gate netlists. | proof (sequential) |
| Formal, result | `fv_result_00/11` (k-induction, depth 3) | All of the above plus **`a_comp`**: at every completion, `result` equals the reference value (R1, R2, R3, R10, R12, R17). See "Result proof" below. **White-box**: run when the DUT has the golden's register names (RTL). A candidate without them reports `unsupported` (non-gating), and its result correctness rests on `eqy_rtl_*`. | proof (sequential + arithmetic) |
| Covers | `fv_cover_00` (14), `fv_cover_11` (15), depth 30 | Each cover is a witness of the condition, and the assertions are proven separately. Covered: power-up busy and power-up result non-zero; a positive, a negative, a 2047 and a −2048 completion; a negative tie; a start while busy; a shift while busy that changes `result`; a shift and `done` on the same edge (the new result wins); back-to-back (start in the `done` cycle); a reset while busy; a hold with a non-zero result. At 11: an overflow or S = −2^19 completion, and an L = 0 completion. At 00: a completion outside A1–A4 (shows that `spec_p` is not vacuously true). | bounded-pass |
| Negative controls | `fv_sanity_pu_00`, `fv_sanity_lat_11`, `fv_sanity_round_00/11`, `fv_sanity_stab_00` | Each must be **refuted** with a trace: power-up state = reset state; a latency of 23; a truncating reference; a 00 claim that ignores A1 (a denominator that moves during the division changes the result). | checker sanity |
| EQY vs golden | `eqy_rtl_00`, `eqy_rtl_11` (RTL), `eqy_rtl` (gate) | `gate/eqy_rtl.eqy`, strategy `sat`, depth 1, one merged partition. Ports and registers are matched by name; the golden's combinational wire names are excluded. **Mandatory** candidate-vs-golden gate (D9b). It is a **strict** equivalence and does not use A1–A4 (section 6). | equivalence proof |
| Structure / interface / lint | `lint_00`, `lint_11` | Yosys on the unoptimised netlist per configuration (`proc -noopt; flatten`): `check -assert`, `scc` empty, forbidden state types. `lint/check_interface.py`: ports, parameter values, flop polarity and clock, no `init`, no black boxes. `lint_11` also elaborates **without** parameters and requires the defaults 1/1 (exit status taken from the check, B1). Verilator `-Wall` via `lint/check_lint.py`. | static |

**`gen` point classes.** For each L of 1, 2, 3, 31, 32, 33, 254, 255, 256, 2047, 2048, 4080,
4094 and 4095:
- small ±S;
- exact ties `32|S| = (2k+1)L` and their neighbours, for 23 values of k from 0 to 2048, both signs;
- the smallest |S| for m = 2046..2049, ±1, both signs (the ±2047/−2048 boundaries);
- S = 127L and −128L (the chip's INT8 bounds).

Then:
- S at the extremes (±524287, −524288, −524287) for L = 1, 255, 4094 and 4095;
- L = 0 with 7 numerators;
- 4,000 fixed-seed random spot checks: half in the chip-like domain, half over the full space.

At 00, the 1,287 points outside A2–A4 are skipped by the simulation; formal covers them (R17).

**`edge_*` testbench.** Every cycle the testbench's own model (written from R1–R11) predicts
`busy`, `done` and `result`. They are compared right after each rising edge and again after the
falling edge, so they must be registered. Around each point:
- `sum_in` is random during busy. The `denominator` is random during busy at 11 and held at 00 (A1).
- Starts while busy (5,223 at 00) and shifts while busy (14,088).
- A shift on the completion edge (1,011).
- Back-to-back starts in the `done` cycle (2,629).
- Idle gaps with shifts.
- Resets in mid-division with `start` and `shift` high (210 aborts).
- 12-bit serial shift-outs checked bit by bit (606).

### Result proof (why it is unbounded, and why it is white-box)

The reference is **`formal/ref_divider_seq.v`**, written from the definition:
- Long division with the **divisor** shifted: L << j is compared with a 24-bit partial remainder
  that starts at Z = 16·|S|.
- Bit 23 is processed at the accept edge, then one bit per edge in lockstep with `cnt`.
- Then the round step (2R >= L), the validity check (m vs 2047/2048) and the sign.

It differs from the RTL, which shifts the dividend through a 12-bit remainder, has no bit 23,
reuses its subtractor for the round step, and applies the sign with an XOR and one increment.
`refcheck` ties the reference to the exact-integer model.

A direct black-box proof of `a_comp` was tried first: k-induction, depth 27, with a combinational
reference. The basecase alone needed about 6 s per step at step 17 and was growing, so it was
stopped (not used as evidence). Instead, `fv_result_*` adds **white-box lemmas** (`l_*`). The
lemma wires are connected to the golden's `state`, `step`, `quotient`, `remainder_value`,
`negative` and, at 11, `g_divisor.saved_divisor` and `invalid_r`, using `connect` in the `.sby`.
With c = `cnt` in 1..24 (c − 1 division steps done), the lemmas assert:
- the control registers: `state`, `step = c − 1`, `negative = S[19]`, the latched divisor and
  `invalid_r`;
- `quotient == ((Z << (c−1)) | (qs >> (24−c)))[22:0]` and `remainder == rs >> (24−c)`;
- the reference's own invariants: low bits of `rs` untouched, no quotient bit set early,
  `qs[23] = 0`, and partial remainder < L.

These lemmas apply while the request is a real division (L != 0, S != −2^19 and, at 00, the
denominator unchanged). They are **assertions, proven together with `a_comp`**, not assumptions.
They make the property set 1-inductive, so depth 3 closes in about 2 s, and the result proof is
unbounded. Lemmas are proof aids, not requirements.

### Assumptions and observer initialisation

There are **no assumptions** (`assume`, `restrict`, `anyconst`, `anyseq`) anywhere.
- All six inputs are free at every step.
- A1–A4 are not assumed. They **condition** the 00 `a_comp` assertion through `spec_p`, which is
  computed from the reference (`rvalid`) and the observed denominator (`lbad`).
- The DUT has no initial value. The `.sby` asserts, after `proc` and before `flatten`, that no
  wire outside the harness carries `init` (`fv_sanity_pu_00` shows the state is free).
- The only initialised registers are the observer `seen` ("a reset edge has been taken") and the
  cover observer `ppl`. The protocol and reference registers are free; they become meaningful at
  the first reset or accept edge.

Single clock: without `multiclock`, SBY updates every flop at each step. This is sound because R15
is checked by lint and by the `.sby` guards, which reject negative-edge, asynchronous, latch and
memory cells after `flatten; opt_clean`. A clock that is still derived after that is refused by
SBY: the run is `inconclusive` (fails closed).

## 5. Result labels (results.json)

Each item has `status` (the contract's own label), `label` (the standard AGENT_CONTEXT label),
`expected_outcome`, `gating` and `ok`. `all_ok` is the conjunction of `ok` over the gating items.
Every item gates, except a `fv_result_*` item that reports `unsupported` on a DUT without the
golden's register names.

| status | label | meaning |
|---|---|---|
| `proven` | `proven` | Unbounded SBY proof with the expected number of assertions in the model, or an EQY PASS |
| `pass-edge-spot` | `pass-sampled` | Every edge/spot point passed with the expected point count. Sampled, not a proof |
| `covered` | `bounded-pass` (`depth: 30`) | Every cover reached. A witness, not a proof |
| `failed-as-expected` | `failed` (`expected_outcome: fail`, `ok: true`) | Negative control refuted with a trace (the named wrong assertion) |
| `pass`, `pass-with-waiver` | `pass-static` | Static check passed (lint, structure, interface, model, generation, refcheck, cell extraction). `pass-with-waiver`: only internal UNUSEDSIGNAL or PDK-model warnings |
| `failed` | `failed` | Check failed. Also used when an engine returned FAIL and SBY could not replay the trace |
| `not-proven` | `inconclusive` | k-induction did not close (SBY UNKNOWN). Not a proof, not a counterexample, not a tool error; `ok: false` |
| `timed-out` | `timed-out` | 900 s formal, 600 s simulation |
| `unsupported` | `unsupported` | `fv_result_*` on a DUT without the white-box names (non-gating) |
| `inconclusive` | `inconclusive` | Tool or infrastructure error, or a job that recorded no result; `ok: false` |

## 6. Running on other designs, gate level

- **Default run.** `run_all.sh` with no arguments runs the golden at 00 and 11 and writes
  `results.json`, `run_all.console.log`, `logs/` and `formal/runs/` here. `logs/` and
  `formal/runs/` are git-ignored. `--rtl FILE` needs `--out DIR` (not this directory). Golden:
  22 gating items, 20 to 56 s with 3 jobs (the machine load average was 40 to 70 from other agents).
- **RTL candidate.** It must keep both parameters (R14). Both configurations run, including
  `eqy_rtl_00` and `eqy_rtl_11`.
- **Gate level.** `--gate --rtl NETLIST --config CC` runs one configuration.
  `gate/extract_cells.py` (the max_reg version, unchanged) builds two views:
  - the simulation view: netlist + PDK Verilog models + UDPs, used by Icarus;
  - the Yosys view: combinational models + liberty flop models, used by lint, SBY and EQY.

  Gate mode runs `cells_prep`, `selftest`, `gen`, `lint_CC`, `refcheck`, `edge_CC`,
  `fv_proto_CC`, `fv_pdr_proto_CC`, the `fv_sanity_*_CC` controls and **`eqy_rtl`**. It does
  not run:
  - `fv_result_*`: white-box, the netlist has no lemma names;
  - `fv_cover_*`: covers are harness reachability, already shown on the RTL, and cost 423 s at
    gate level.

  A gate netlist's arithmetic therefore rests on `eqy_rtl` (proof) and `edge_CC` (sampled).
- **EQY (`gate/eqy_rtl.eqy`).**
  - Both sides get `proc; prep; dffunmap`.
  - Ports and registers are matched by name. The golden's combinational wire names (`trial`,
    `difference`, `next_quotient`, …) are excluded, because a netlist may keep such a name on a
    net that ABC optimised under a don't-care.
  - All partitions are **merged** into one. Separate partitions would treat `busy`, a function
    of `state`, as an independent input and give spurious "unknown" results.
  - PASS means every matched register's next state and every output are equal given equal
    matched state: an unbounded equivalence.
  - Limits:
    - A netlist that re-encodes or renames the golden's state fails (equivalence unknown) and
      would need its own reviewed match.
    - EQY cannot see clock polarity; lint and the `.sby` guards check it.
    - **EQY is strict.** It does not use A1–A4, so a 00 candidate that exploits those don't-cares
      fails `eqy_rtl_00` and needs a reviewed domain-restricted equivalence. One candidate
      route is a `fv_result_00`-style proof of the candidate against the same reference.
- **Golden netlists.** Made with `gate/synth_gf180.sh <out.v> <00|11> [rtl.v]` (the
  `synth_area.py` recipe with `chparam`):
  - `gate/netlists/divider_00_gf180.v`: 8,853.24 µm², 56 `dffq_1`;
  - `gate/netlists/divider_11_gf180.v`: 10,602.82 µm², 69 `dffq_1`;
  - `divider_00_clkbuf_gf180.v`: the 00 netlist with one `clkbuf_1` from `clk` to all 56 flops,
    as CTS produces it; it must pass.

  `synth_area.py`, which reads all seven chip sources, reports 8,804.95 µm² for 00 with the same
  recipe. ABC's result depends on the input set; the difference does not affect the contract.
  Evidence: `gate/evidence/{golden_00_gf180,golden_11_gf180,clkbuf_00}/`.

## 7. X (4-state) behaviour

X/Z inputs are not specified. Before the first reset the state is X in Icarus and free in formal.
The X check of `busy`, `done` and `result` after the first reset is the Icarus `!==` comparison
in `edge_*` at every cycle: directed and sampled, not exhaustive. SBY is 2-state, and EQY treats
an X constant as a free value, so neither is an X check.
