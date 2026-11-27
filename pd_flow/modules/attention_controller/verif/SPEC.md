# attention_controller: verification contract (Agent 1)

Golden: `../snapshot/attention_controller.sv` together with the frozen submodules in `../snapshot/`
(mac_unit, ripple_add, max_reg, exp_lut, divider) and `project.v` (the TT top). The contract is
`run_all.sh`; it writes `results.json`. This file defines the requirements and states what each
item proves. `RTM.md` maps requirements to items.

**Scope choice.** The controller is verified **with its frozen golden submodules** and not with
black boxes. There are three reasons:
- The A1–A4 obligations are about values that the submodules compute: L, O0 and W.
- The proofs closed in seconds with the submodules in place.
- A candidate that changes a submodule is still compared against the full golden by `equiv_P`.

`run_all.sh --rtl X` appends to X every submodule it does not define, taken from the snapshot.

## 1. Notation

- `P = OUTPUTS`, which is 8 when shipped; 4 and 2 are also legal. `B = log2 P`.
- `pos` is the 10-bit clock counter. A **run** goes from an accepted `start` until `idle`.
- A **fresh** run has `cont = 0`. A **continue** run has `cont = 1`.
- The **held inputs** are `last`, `score_shift` and `cont`. They are *held* when they are unchanged from the accepted start until the run ends (header: "must be held from start until idle").
- Every statement holds **after the first reset**: from the first rising edge with `rst_n = 0` on. Behaviour before that edge is unspecified (section 2.5).

## 2. Requirements

### 2.1 FSM (states IDLE, RESTART, CMD, SCORE, VALUE, DIV_START, DIV_WAIT, OUTPUT)

| R | Requirement |
|---|---|
| T1 | Reset: an edge with `rst_n = 0` gives IDLE, CS# high, SCK low and `score_done = 0`. |
| T2 | IDLE without start holds. Start with `cont = 0` → RESTART, with token 0, `pos = 0` and pass 1. Start with `cont = 1` → SCORE, with token 0, `pos = 0`, pass 2, and an SCK rise in that clock. |
| T3 | RESTART → CMD after 1 clock, with CS# high during RESTART. CMD lasts `pos` 1..161 and then goes to SCORE with `pos = 0`. |
| T4 | SCORE runs a 1024-clock row (pos 0..1023). Pass 1: at the row end, the token goes up by 1, or wraps to 0 and pass 2 begins when `token == last`; the state stays SCORE. Pass 2: the row end → VALUE. |
| T5 | VALUE runs a V block of `8P` clocks. At its end: `token == last` → DIV_START with `output_index = 0`; otherwise token + 1 → SCORE. |
| T6 | DIV_START waits until `pos[B-1:0] == output_index` (the ring head is the component), then → DIV_WAIT. The divider is started in that same clock. |
| T7 | DIV_WAIT → OUTPUT on `div_done`, exactly 25 clocks after the accept edge. |
| T8 | OUTPUT holds until `out_ready`. Then `output_index + 1`, and → DIV_START, or → IDLE after component P−1. |
| T9 | Ring phase: from the first clock after CMD (or after a continue start) until the run ends, `pos[B-1:0]` steps by +1 mod P on every clock. A row is 1024 clocks and a V block 8P, both multiples of P, so the phase is never broken. |
| T10 | The divider is busy or done exactly while in DIV_WAIT (`(busy ∨ done) == DIV_WAIT`). |

### 2.2 SPI pins (flash: 0x6B Fast Read Quad Output, address 0, 8 dummy clocks, mode 0)

| R | Requirement |
|---|---|
| S1 | `spi_cs_n` is low exactly from the end of RESTART until reset. It stays low across runs: a continue run reuses the open read. |
| S2 | SCK is high for one clock: in CMD at `pos % 4 == 2`, and in SCORE/VALUE at `pos % 4 == 0`. That gives SCK = clk/4. There are 41 rises in CMD (8 command + 24 address + 8 dummy, plus the first data nibble). The final nibble of a run has no rise. |
| S3 | `spi_mosi_oe` is high exactly while in CMD with `pos < 128`, which covers the 32 command and address bits. |
| S4 | While driven, `spi_mosi` is bit `31 − pos[6:2]` of `0x6B000000`, MSB first. It changes on the clock after an SCK high. |
| S5 | Capture: each SCK rise samples `spi_io[3:0]` (high nibble first). The serial bit is the captured nibble, MSB first, one bit per clock (`s_cap`). |
| S6 | The pin timing equals an independent segment reference (`formal/ref_ctrl.v`) at every clock. This applies to idle, CS#, SCK, IO0 enable, IO0 value when enabled, and out_valid (`a_ports`). |

### 2.3 Controls to the submodules per state

| R | Requirement |
|---|---|
| C1 | mac_unit:<br>- `accum_mode = (state ≠ SCORE)`;<br>- `load` in the first 8 clocks of a score row;<br>- `score_en = SCORE ∧ pos[3]`;<br>- `first = (token == 0)`;<br>- `accum_en = VALUE`;<br>- `sel = pos[B-1:0]`;<br>- `bit_sel = ~pos[2:0]` in SCORE and `~pos[B+2:B]` in VALUE;<br>- `subtract = second_pass`.<br>After the 8 load clocks: S = 0 in pass 1 and S = M in pass 2, with M unchanged (`t_load`). |
| C2 | max_reg is updated once per pass-1 row, at its end, in token order (`t_p1_tok`). `first` is set for token 0. |
| C3 | The V block of token t meets component c at the ring head. With the head = `pos[B-1:0]` (T9), V bit plane b of component c is shifted in exactly while `sel = c`. |
| C4 | exp_lut `W` is constant across a V block when `score_shift` is held (`q_weight`). |
| C5 | divider: `start` only in DIV_START at the head phase; `shift = out_shift ∧ out_valid`. |

### 2.4 Output serialisation

| R | Requirement |
|---|---|
| O1 | `out_valid == (state == OUTPUT)`, `idle == (state == IDLE)` and `out_bit == result[11]`. |
| O2 | `result` changes only at a divider completion, or by one left shift with zero fill on each `out_shift` while out_valid. Otherwise it holds (`o_shift`). |
| O3 | Component order 0..P−1. Each is a 12-bit signed value (INT8.4), MSB first. Its value is the chip_attention model's (Python), checked by `e2e_P` and pinned to the golden by `equiv_P`. |

### 2.5 Reset and power-up

| R | Requirement |
|---|---|
| P1 | Reset is synchronous. The reset registers are `state`, `flash_open`, `spi_sck` and `score_done`, plus the divider's own reset of state and done. |
| P2 | The **non-reset** registers are:<br>- controller: `pos`, `nibble`, `q`, `token`, `second_pass`, `output_index`;<br>- mac_unit: ring, S, L;<br>- max_reg: M;<br>- divider: data registers.<br>This is safe because each one is written before it is read, after the reset.<br>- `pos`, `token` and `second_pass` are set by the accepted start.<br>- `nibble` is set at the first SCK rise.<br>- `q` is shifted in before its first use.<br>- S is loaded in the first 8 clocks of every row.<br>- M is rewritten by every fresh run (token 0 has `first`).<br>- L and the ring are loaded by token 0 (`first`).<br>- `output_index` is set at the run end.<br>- The divider data is loaded at the accept edge.<br>Proven by `seq_eq_P`: its freshness observers show every port equals the golden from the anchor on. Proven also by the int_P invariants, which all hold from an arbitrary non-reset state. |
| P3 | Behaviour before the first reset is unspecified. A candidate may differ there, and TT holds `rst_n` low at power-up. A candidate may **not** add state whose power-up value is visible after a reset. The flop bound (section 4) enforces this. |
| P4 | **Host rule H1.** A continue run is legal only right after a completed run, with no reset in between. Reset clears `flash_open` but not M, so a continue run after a reset reads garbage (RTL header). Outputs of such runs are outside the contract and are not compared by `seq_eq` (`f_M`). |
| P5 | A reset mid-run aborts it: next clock IDLE, CS# high, SCK low and IO0 released. The next run starts clean (`e2e_P` reset case; `cov_g5`–`g9` reach a reset in every state). |

### 2.6 TT top (`project.v`)

| R | Requirement |
|---|---|
| E1 | The fixed pins hold:<br>- RAM chip selects high and driven;<br>- IO1..IO3 are inputs;<br>- SCK and CS# are driven;<br>- `uio_oe[1] = spi_mosi_oe`;<br>- unused outputs are 0 (`tp_pins`). |
| E2 | `ena = 0` or `rst_n = 0` holds the core in reset: idle, CS# high, SCK low, IO0 released, DRDY low (`tp_reset`). |
| E3 | The configuration chain (`last`, `score_shift`, `cont`) is held from the accepted start until the core is idle (`tp_held`), and never shifts at a start edge (`tp_noshift`). **This discharges the held-input condition** of 2.3/A2/A4 at the chip level. |

### 2.7 Interface, structure, lint, equivalence

| R | Requirement |
|---|---|
| I1 | The ports and the `OUTPUTS` parameter are exactly the golden's. The default is 8. |
| I2 | Every flop is a positive-edge D flop on `clk`, with sync reset or enable allowed. There are no async flops, latches, memories, init values or black boxes, and no combinational loop. |
| I3 | Flop bits ≤ the golden's: 308 / 227 / 186 at P = 8 / 4 / 2. This rules out hidden state (mac F1). |
| I4 | Verilator `-Wall` is clean except the waived class: an unused internal bit. The golden has two of these, ripple_add `c[22]` and divider `difference[12]`. |
| Q1 | `equiv_P = eqy_rtl_P OR seq_eq_P` (section 6). |

## 3. Divider assumptions A1–A4 (divider SPEC, LATCH_DENOMINATOR = 0): discharge

| A | Obligation | Status | Evidence |
|---|---|---|---|
| A1 | `denominator` (L) is constant from the accept edge to the completion edge. | **Proven, unconditional** (after the first reset, any inputs, held or not). | `a1_stable`: `busy → L == L at accept`. `j_div`: busy only in DIV_WAIT, where `accum_en = 0`. In `int_P` for P = 8, 4, 2. |
| A2 | L ≥ 1 | **Proven: L = Σ W, conditional on held inputs (E3) and tape assumption T1.** | `a2a_sum` (under held inputs): at every accept edge, L equals the sum of W over tokens 0..last, each exactly once (`f_vcnt = last + 1`). It does not wrap (`l_p2`, `l_after`: ≤ 255·(t+1) < 4096), and L ≥ max W. Hence **L ≥ 1 ⇔ some token of the run has W ≥ 1**: this is tape assumption **T1**. |
| A3 | `sum_in` ≠ −524288 at the accept edge. | **Unconditional by composition.** | The facts used:<br>- each V bit is accumulated once into its component: T9 `q_phase`, C3, `t_value_step`;<br>- `first` is token 0;<br>- W ≤ 255;<br>- at most 16 tokens;<br>- mac R5–R10.<br>So \|O0\| ≤ 16·255·128 = 522,240 < 2^19. This is not a single formal item; it composes proven controller facts with the frozen mac contract. |
| A4 | The rounded quotient is in range. | **By composition, conditional on held inputs and T1.** | The facts used:<br>- W is constant per V block (`q_weight`);<br>- O0 = Σ_t W_t·v_t over the same tokens as L (A2 proof);<br>- O0/L is a weighted average of INT8 values.<br>So 16·O0/L ∈ [−2048, 2032]. This is not a single formal item. |

**Tape assumption T1** (minimal): in every run, at least one token t ≤ last has W_t ≥ 1.

**Sufficient condition T1'**, which is a valid tape plus host rule H1:
- the pass-2 score rows equal the pass-1 rows byte for byte;
- `last` is the same across a fresh run and its continue runs.

Under T1', the argmax token has D = M − S = 0, so W = 255 and L ≥ 255.

T1 depends on the tape, so it cannot be proven from the controller alone. It is the only tape assumption. Outside T1 the divider's result is a don't care (divider R17), which affects only the value, never the timing: T7 still holds, because `r_dw` is proven for any inputs.

## 4. Items (`run_all.sh`, at most 3 jobs)

| Item | What | Label |
|---|---|---|
| `gen` | Vectors from the Python model per P: 3 cases, 4 runs.<br>1. 1 token at extremes.<br>2. 2 random tokens, chunk 0 fresh, then chunk 64/P−1 as a continue run.<br>3. 3 tokens with a reset mid-run, then a clean run. | pass-static |
| `lint_P` | I1–I4. At P = 8 it also checks the default parameter. | pass-static |
| `e2e_P` | Port-only end-to-end run against a flash model and a host model (section 8). | pass-sampled |
| `fv_int_P` | 54 assertions, k-induction (depth 3), golden internal (section 5). Covers T1–T10, S1–S6, C1–C5, O1–O2, A1, and A2 = L sum. | proven |
| `fv_cov_gN_P` | 30 covers in 9 groups (section 7): every state, every transition, the pass 1 → 2 switch, CS# fall and rise, an out_shift, and a reset in every non-IDLE state. | bounded-pass |
| `fv_sanity_{mosi,cap,sck}_8` | Negative controls:<br>- the command is 0xEB;<br>- the capture is one nibble late;<br>- SCK uses the wrong phase.<br>Each must be refuted. | failed (as expected) |
| `fv_top_8` | E1–E3, 4 assertions, k-induction. It runs for every DUT at P = 8. | proven |
| `fv_sanity_top_8` | Negative control: the chain is claimed never to shift (wrong). | failed (as expected) |
| `eqy_rtl_P` | EQY against the golden: names matched, one merged partition, sat depth 1. | constituent |
| `seq_eq_P` | Reset-anchored miter against the golden (section 6). | constituent |
| `fv_sanity_seq_P` | Miter negative control: IO0 compared even while released. | failed (as expected) |
| `equiv_P` | `eqy_rtl_P` OR `seq_eq_P` proven. | proven |
| `lemma_lint`, `cells_prep` | Lemma whitelist (divider F1/F2); the netlist views (gate mode). | pass-static |

`results.json` uses the mac/divider schema: `status`, `label`, `gating`, `expected_outcome`, `part_of`, `scope`.

**Golden-only items** are `fv_int_*`, `fv_cov_*` and the internal sanity items. They read golden internals, so they run only when the DUT's sha256 equals the snapshot's. **A candidate inherits them through `equiv_P`**:
- `eqy_rtl` is a strict equivalence;
- `seq_eq` equates every port after the first reset: out_bit whenever the golden's result is reset-fresh, and IO0 whenever it is driven.

The port properties therefore transfer.

## 5. fv_int_P (golden internal, no assumptions)

The props file `formal/ctrl_int_props.vh` is included into a copy of the golden. The submodules are read without `-formal`.

Guards:
- **F1:** no assume, anyconst or anyseq cells.
- Init values only on harness `f_*` registers.
- `proc -norom`: the exp_lut table stays logic. A ROM would be free state under induction.
- `connect -nounset` for the read-only divider taps. Plain `-set` leaves the readers free, which is unsound; a toy SBY demonstrated this.

The observers start at the first reset (`f_rs`). Every invariant is guarded by `f_rs`, so it holds from an arbitrary power-up state.

`a_ports` compares the pins with `ref_ctrl.v`. The relational invariants `r_*` (segment = state, counters, token, phase, divider step) close its induction.

The held-input observer `f_h` records last, score_shift and cont at the accepted start. The `v_*` and `a2a_sum` items are asserted under `f_h`. Without held inputs the token wraps and the count is meaningless.

E3 proves that the TT top always holds them.

## 6. seq_eq_P (`formal/ctrl_miter.sv`)

The golden (renamed `gold_*`) and the DUT both start in free, independent states. They share every input.

Anchor `an` = the first reset edge. From then on, `a_eq` requires these to be equal:
- idle, CS#, SCK, IO0 enable and valid;
- IO0 when enabled;
- `out_bit` when the golden's divider result is fresh (`f_res`).

The freshness observers (`f_ctl`, `f_oi`, `f_nib`, `f_q`, `f_S`, `f_M`, `f_L`, `f_ring`, `f_req`) follow the golden's control signals, which are tied in by `connect -nounset` (`seq_gold.ys`).

There are no assumptions. The DUT is read without `-formal`. The guards are F1, a check that the miter has no asserts outside the harness, an init guard, a check for no `$mem`, and flop guards.

Lemmas (optional, `--lemmas`) are assertions only. The observer whitelist is applied by `lemma_prep.py`.

The golden self-check uses `formal/golden_self_lemmas.sv`: 24 lemmas at P = 8, 20 at P = 4 and 18 at P = 2. With no lemmas the item normally ends not-proven (inconclusive) for a restructured candidate. That is expected; `equiv_P` then rests on `eqy_rtl_P`.

## 7. Covers

The groups are run by abc bmc3 with a deterministic host driver (`formal/cover_top.sv`). Its only input is the clock. The driver plays a short legal protocol, which makes deep covers (about 1,300 clocks) take seconds.

Each group asserts that its cover bits are *not* all sticky-set (`w_group`). A refutation trace is the witness that the group's covers are all reached after a reset. The trace is replayed with z3 and saved under `formal/runs/`.

| Group | Covers |
|---|---|
| g1 | A continue run with all P results. |
| g2 | A fresh run: start, CS# fall, command, the next pass-1 token. |
| g3 | Pass 1 → pass 2. |
| g4 | The next pass-2 token. |
| g5 | CS# rise, and a reset in RESTART, CMD and SCORE. |
| g6–g9 | A reset in VALUE, DIV_START, DIV_WAIT and OUTPUT. |

The covers witness reachability under this driver only. Safety does not depend on them.

## 8. End-to-end simulation (`sim/tb_e2e.sv`, seconds)

The DUT is driven at its ports only, against a quad flash model holding the Python tape. The host reads each 16-bit frame at an uneven pace.

Checks:
- every result bit, against `chip_attention`;
- the command and address;
- the IO0 drive window and contention;
- SCK mode 0;
- the run length in SCK rises;
- idle after the run;
- quiet outputs after a mid-run reset.

RTL runs on Icarus (4-state). Gate runs on Verilator (2-state) with random power-up, seeds 1 and 7, on the Yosys view.

## 9. Gate mode

`run_all.sh --rtl net.v --gate --config P --out DIR` takes a flattened GF180 netlist. `gate/extract_cells.py` builds:
- the simulation view (cell UDPs);
- the Yosys view (liberty flop models).

The gate run checks the following:
- lint and flop bound;
- `e2e` on Verilator;
- `fv_top_8`;
- `eqy_rtl` against the golden RTL, with register names matched;
- `seq_eq` without lemmas (constituent);
- `equiv`.

The golden reference netlist is `gate/netlists/attention_controller_8_gf180.v`, from `gate/synth_gf180.sh` (synth `-nofsm`; area 40,448.8 µm² TT). Its gate-mode evidence is in `gate/evidence/golden_8_gf180/`: 7/7 gating ok.

With FSM recoding (`synth` default), the netlist has 314 flops, so the flop bound rejects it. The state names are also lost, so EQY cannot match them.

Notes:
- The PDK UDP flop view mis-simulates under Verilator (160 spurious mismatches, the one-cycle skew documented in the mac_unit contract). On Icarus it is X-pessimistic. So gate e2e uses Verilator 2-state on the Yosys view, which has the liberty flop models, as the mac contract does. That view gives 0 errors. No formal X-propagation check is done.
- EQY needs one merged partition. With separate partitions, matched names that the netlist also reads internally become free cut points, which gives spurious failures on a correct netlist.

## 10. Assumptions and limitations

- **No formal assumptions anywhere.** The conditions are:
  - **after first reset** (all items);
  - **held inputs** for `v_*`/`a2a_sum`/`q_weight`, discharged at the top by E3;
  - tape assumption **T1** for A2/A4;
  - host rule **H1** for continue runs.
- A3 and A4 are discharged by composition with the mac contract and the arithmetic bound, not by one end-to-end formal item.
- The values of out_bit (the arithmetic) are pinned by `equiv_P` to the golden and spot-checked by `e2e_P` (3 cases per P). No formal item proves the numeric result against the Python model.
- `eqy_rtl` (sat, depth 1) proves equivalence from matched-equal register states. A candidate must keep the golden register names (state, pos, token, nibble, the mac and divider register names) or supply `seq_eq` lemmas.
- Behaviour that differs only in the first clock after power-up is invisible to `eqy_rtl` depth 1. Probe `x_pu`: an extra flop that flips out_bit only in clock 0. EQY accepted it, which is correct, because out_valid is low then. The flop bound I3 rejected it.
- Covers are bounded and driver-specific. A reset during CS# fall/rise is covered only in g5.
- The gate run was demonstrated only for P = 8 (the shipped configuration). `fv_top_8` checks the top only at OUTPUTS = 8.

## 11. Self-check

The golden contract was run twice from clean, with identical item statuses. The run times are in RTM.md.

Smoke mutants (`--rtl mutant --out scratch`) were all killed (exit 1):

| Mutant | Change | Killed by |
|---|---|---|
| m1_cmd | command 0x6B → 0x6D (wrong zero-bit pattern) | e2e_8/4/2, eqy_rtl_*, equiv_* |
| m2_lupd | `accum_en` also in DIV_WAIT | e2e_*, eqy_rtl_*, equiv_* |
| m3_oe | IO0 enable leaks into dummy clocks (`pos[7] ∧ pos[3]`) | e2e_*, eqy_rtl_*, equiv_* |
| x_pu (probe) | power-up-only out_bit flip, one extra flop | lint_* (flop bound 309 > 308) |
