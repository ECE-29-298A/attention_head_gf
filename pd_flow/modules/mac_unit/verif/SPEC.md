# mac_unit: verification contract (Phase 1, Agent 1)

Golden (immutable): `../snapshot/mac_unit.v` (sha256 `221110a1…`) with the frozen sub-block
`../snapshot/ripple_add.v` (contract `ripple_add` b879560878477abf). The chip uses `OUTPUTS = 8`
(`attention_controller.sv` lines 98–104); `OUTPUTS = 2` and `4` are legal and checked.
Built under D9/D9b:
- the state update is sequential, so the next-state equations are SBY proofs;
- the arithmetic gets edge cases plus spot checks;
- EQY (or the `seq_eq` miter) against the golden is mandatory.

## 1. Notation

- `P = OUTPUTS`. `b = bit_sel` (0–7).
- `w(b)` is the two's-complement weight of bit `b` of a byte: `2^b` for `b < 7`, and `-128` for `b = 7`.
- `sx_n(x)` is `x` read as an n-bit signed number. All results wrap: S mod 2^22, L mod 2^12, ring slots mod 2^20.
- The state is S (22 bits), L (12 bits) and the ring of `P` 20-bit slots. Slot 0 is the head, `O0`.
- Every equation gives the value after the rising edge of `clk`, as a function of the state and the inputs before it.
- No reset exists. The state at power-up is arbitrary.

## 2. Requirements

| R | Requirement |
|---|---|
| R1 | **Score accumulate.** If `accum_mode = 0`, `score_en = 1` and `load = 0`: `S' = S + qi·ki[b]·w(b)` when `subtract = 0`, and `S' = S − qi·ki[b]·w(b)` when `subtract = 1`. `qi` is signed; only bit `b` of `ki` is used. |
| R2 | **Bit-7 sign handling.** `w(7) = −128`: the MSB of `ki` is the two's-complement sign bit, so with `subtract = 0` a set `ki[7]` subtracts `128·qi`, and with `subtract = 1` it adds `128·qi`. Over a row (bits 7…0 of each K byte, MSB first), pass 1 (`load` with `subtract = 0`) ends with `S = Σ q·k`, and pass 2 (`load` with `subtract = 1`) ends with `S = M − Σ q·k`. Checked in `selftest` for 64-dim extremes. |
| R3 | **Load forms.** `load = 1` gives `S' = subtract ? M : 0`, in either mode. It has priority over `score_en`. |
| R4 | **score_en in accumulate mode** (off-protocol, but defined): if `accum_mode = 1`, `score_en = 1` and `load = 0`, then `S' = (h + t) mod 2^22`, where `h` and `t` are the accumulate terms of R5/R6. That is the value of the shared adder. |
| R5 | **Accumulate term.** `t = W·v[b]·w(b)` if `accum_en = 1`, and `t = 0` otherwise. `W` is unsigned; `v` is a two's-complement byte, so bit 7 subtracts `128·W`. |
| R6 | **First-token load.** `h = 0` if `accum_en ∧ first ∧ b = 7` (the first token's bit 7 loads the slot instead of adding). Otherwise `h = sx_20(O0)`. `first` with any other bit adds normally. |
| R7 | **Ring rotation.** The ring turns on every clock, whatever the inputs: slot j takes slot j+1 and the tail (slot P−1) takes the new value `tail`. Seen at the ports: **`O0(t+P) = tail(t)`**. |
| R8 | **Accumulate mode** (`accum_mode = 1`): `tail = (h + t) mod 2^20`. With `accum_en = 0` this is `O0`, so the ring holds its sums. |
| R9 | **Score mode** (`accum_mode = 0`): `tail = O0`. The ring bypasses the busy adder and keeps its sums, whatever `accum_en`, `first`, `W` and `v` are. |
| R10 | **L update.** If `accum_en ∧ sel = 0 ∧ b = 0`: `L' = ((first ? 0 : L) + W) mod 2^12`. Otherwise L holds. Independent of `accum_mode`. `sel` is used **only** here. |
| R11 | **S hold.** `load = 0 ∧ score_en = 0` gives `S' = S`. |
| R12 | **O0 alias and Moore outputs.** `O0` is the ring head: no logic between a state bit and the port. `S`, `L` and `O0` are registers; R1–R11 leave no room for an input to reach an output in the same cycle (`a_S`, `a_L`, `a_O0` would fail). |
| R13 | **Interface.** Parameter `OUTPUTS` (default 8; 2, 4, 8 legal). Ports exactly: `clk`, `accum_mode`, `load`, `subtract`, `M[21:0]`, `score_en`, `qi[7:0]`, `ki[7:0]`, `first`, `accum_en`, `W[7:0]`, `sel[$clog2(P)-1:0]`, `v[7:0]`, `bit_sel[2:0]` in; `S[21:0]`, `L[11:0]`, `O0[19:0]` out. No reset port. |
| R14 | **Power-up and structure.** Every state element is a plain positive-edge D flop on `clk`: no asynchronous or synchronous reset or set, no latch, no memory, no initial value. **A candidate may not change the power-up behaviour of the ring, S or L.** They power up arbitrary, and from every power-up state the behaviour is the golden's (R1–R12, proven from any start state). Adding a reset, an `initial`/init value, or a dependence of later behaviour on a hidden power-up state is a contract violation. |
| R15 | **Lint.** Verilator `-Wall` has no warning except the waived class: an unused internal (non-port) bit. In the golden that is ripple_add's dropped carry `c[N]`. A Yosys structural check finds no combinational loop and no forbidden cell. |
| R16 | **Equivalence with the golden:** `equiv_P = eqy_rtl_P OR seq_eq_P` (section 5). |

How the controller drives the unit, for meaning only; nothing in the contract assumes it:
- `accum_mode = (state != SCORE)`;
- `load` in the first 8 clocks of a score row;
- `score_en = pos[3]`;
- `ki = v = {8{serial bit}}` with `bit_sel = ~pos[2:0]` or `~pos[P+2:P]` (MSB first);
- `sel = pos[P-1:0]`, free-running, so the head is component `sel`;
- `first = (token == 0)`;
- `accum_en = (state == VALUE)`.

The ±522,240 bound on `O0` (16 tokens × 255 × 128) keeps the 20-bit slots from wrapping, but the contract specifies the wrap anyway.

## 3. Items

All items are in `run_all.sh`, run with at most 3 jobs. RTL mode covers P = 8, 4 and 2; gate mode covers the one P given by `--config`.

| Item | Kind | Gating | What |
|---|---|---|---|
| `selftest` | model | yes | The Python model (`model/golden_model.py`) against the high-level meaning: dot products in pass 1 and 2 (64-dim extremes and random), per-component V sums (16 tokens at ±extremes), L sums, and 15 hand-computed steps. 153 checks. |
| `gen` | model | yes | Edge and spot vectors per P, plus 4,024 reference points (fixed seed 7). |
| `refcheck` | sim | yes | `formal/ref_mac_next.v` (the formal reference) against the Python model on 4,024 points. These are two independent writings of R1–R12. |
| `lint_P` | static | yes | R13, R14 (structure, no init, no reset), R15. At P = 8 in RTL mode it also checks the default `OUTPUTS = 8`. |
| `lemma_lint` | static | yes (when lemmas given) | The lemma file is assertions only (section 5.3). |
| `edge_P` | sim | yes | About 10–12k cycles per P, each one compared against the model. The cycles cover: a power-up flush; controller-form score rows (64-dim ±128, extremes, both `ki` forms, pass 1 and 2, M extremes); 16-token V accumulation at ±extremes with score rows in between and hold read-outs; single-step `qi × ki × bit_sel 0..7 × subtract` extremes; single-step `W × v × bit_sel × first` with holds; L with `sel` 0 and ≠0, `bit_sel` 0/7/3, `first`, and wrap past 4095; mode switches and off-protocol mixes; 2,000 random cycles. RTL runs on Icarus 4-state (known outputs compared with `!==`). Gate runs on Verilator 2-state with random power-up, 2 seeds. |
| `fv_spec_P` | formal | **yes, every DUT** | R1–R12 as `a_S`, `a_L`, `a_O0` from **any DUT start state**, k-induction (section 4). |
| `fv_cover_P` | formal | yes | 18 covers (depth P+3), all reached: loads, bit-7/bit-0 signs, wrap, hold, score_en in accumulate mode, a first-token load followed to the head (−255·128), accumulate, ring hold while scoring, and the L first/add/wrap/sel-hold/bit-hold cases. |
| `fv_sanity_{sign,lsel,delay}_8` | formal | yes | Negative controls: the reference with w(7) = +128, the L condition without `sel = 0`, and O0 checked P−1 edges later. Each must be refuted with a trace. |
| `eqy_rtl_P` | formal | constituent | EQY against the golden (section 6). |
| `seq_eq_P` | formal | constituent | Flush-anchored sequential miter against the golden (section 5). |
| `fv_sanity_seq_P` | formal | yes | Negative control of the miter (S off by one), which must be refuted. |
| `equiv_P` | derived | yes | `eqy_rtl_P` proven OR `seq_eq_P` proven. |
| `cells_prep` | gate | yes | Gate mode only: builds the netlist views (`gate/extract_cells.py`, the max_reg copy). |

Status labels map to the AGENT_CONTEXT labels in `results.json` (`label`). `covered` maps to bounded-pass, and `pass-edge-spot` maps to pass-sampled.

## 4. Formal specification (fv_spec, black-box, any start state)

`formal/mac_props.sv` instantiates the DUT by its ports only and evaluates `formal/ref_mac_next.v` on the DUT's current `S`, `L`, `O0` and inputs. The reference uses signed bit weights and small products, with no shared adder and no `~x + 1`. The harness registers the results and asserts:
- `a_S`: `S(t+1) = S_n(t)` (R1–R4, R11);
- `a_L`: `L(t+1) = L_n(t)` (R10);
- `a_O0`: `O0(t+P) = tail_n(t)` (R5–R9, R7 as seen at the port), via a P-deep queue of expected tails.

4.1 **No assumptions and a free start.**
- All inputs are free.
- `mac.sby` rejects any formal cell other than the harness's own assert/cover, anywhere (the divider's F1 guard, applied here too). It also rejects any `init` on a DUT wire, and any async, negative-edge or latch element.
- The DUT is read **without** `-formal`, so `` `ifdef FORMAL `` logic in a candidate is not compiled in.
- Because the DUT has no initial value, every DUT state is an initial state, so the proofs hold from any power-up state (R14).

4.2 **Why k-induction closes for any DUT.** Each assertion compares a DUT output with a value the harness computed at most P edges earlier inside the same trace, and the harness's own state (`pv`, `cnt`, the tail queue) is only trusted once it was written in-trace. Every DUT state is initial, so a depth-(P+3) induction step reduces to the base case. It closes for the golden, the GF180 netlists and every smoke mutant, in 3–11 s.

4.3 **Completeness.** For any DUT that passes, its port trace from any start state equals the golden's trace from the start state (S(0), L(0), ring = O0(0), …, O0(P−1)): the recurrences of R1–R10 determine the trace uniquely once those values are fixed. A candidate that passes `fv_spec_P` therefore behaves at its ports as the golden does from some power-up state. The direction "every golden power-up state is reachable" is enforced structurally: no init (lint and `.sby` guards) and no reset port (R13). One residual gap, about the first P−1 cycles of O0, is in section 7.

## 5. seq_eq: flush-anchored sequential equivalence (no reset)

5.1 **Anchor.** mac_unit has no reset, so the divider's reset anchoring does not apply. The two alternatives:
- "Start in corresponding states" would need an initial-state assumption, or a candidate-written correspondence that is assumed at step 0. Either one constrains the miter, and the F1 rule forbids that.
- Instead, `formal/mac_miter.sv` starts **both instances in free, independent states**. Harness observers track, from the inputs alone, which golden outputs have become functions of the inputs only:
  - `fresh_s`: set by `load`; in accumulate mode, `score_en` copies the head freshness;
  - `fresh_l`: set by an L update with `first`;
  - `fresh_ring[P]`: a slot becomes fresh when written from a fresh head or by a first-token load, and the vector rotates with the ring.
- `a_eq` compares S, L and O0 whenever each is fresh.

It is sound in both directions that matter:
- A candidate equivalent to the golden from corresponding states must pass for every pair of start states. A fresh output depends only on the inputs.
- Passing means every consumed value matches. The controller loads S before each score, loads L at token 0, and loads every ring slot at the first token's bit 7; that is the flush this anchor models, generalised to any input sequence.

Without lemmas, k-induction at depth P+3 closes for any candidate whose state is visible at its ports within P edges. The golden and the GF180 netlists prove in 1–8 s.

5.2 **Power-up.** `seq_eq` does not compare outputs before the flush. Power-up behaviour is pinned for every DUT by the gating `fv_spec_P` (section 4.3) and by the structure checks (R14). **A candidate is not allowed to change the power-up behaviour of the ring, S or L:** no reset, no init, and behaviour from every power-up state as in R1–R12. A gate netlist that `eqy_rtl` fails, for example after a state re-encoding, can therefore reach `equiv` through `seq_eq`, but it is still gated by `fv_spec`.

5.3 **Lemmas** (`--lemmas FILE`). The tooling is adapted from the frozen divider tooling, including review fixes F1 and F2.
- Statements are `assert property (expr);`. `expr` may use `gold.*` and `cand.*` names, the read-only observers `fresh_s`, `fresh_l` and `fresh_ring[...]`, literals, `$signed`/`$unsigned` and pure operators. `// @config 2|4|8|<list>|all` selects configurations.
- A token whitelist rejects everything else: other identifiers, assignment and side-effecting operators, and temporal operators.
- Lemmas are **asserted** from step 0 together with `a_eq`, never assumed. Because the start states are independent, a useful lemma must be guarded by a `fresh_*` observer.
- `formal/golden_self_lemmas.sv` is the default for the golden DUT. It exercises the lemma path; the induction also closes without it. `seq_eq.sby` allows no formal cell except assertions (F1). Both designs are read without `-formal`. Neither instance may carry an init value.

## 6. Gate mode and EQY

- `gate/synth_gf180.sh <out.v> <P>` is the divider recipe: `synth -flatten`, `dfflibmap`, `abc -liberty`, TT 025C 3V30, `write_verilog -noattr`. Ports stay vectors. `mac_unit_8_gf180.v` is 20,573.4144 µm², which equals the PHASE0 audit figure; `mac_unit_2_gf180.v` is 12,929.73 µm².
- `run_all.sh --gate --rtl <netlist> --config P --out DIR` runs these items:
  - `cells_prep` (simulation view with PDK UDPs; Yosys view with liberty flop models);
  - `lint_P`;
  - `edge_P` (Verilator);
  - `fv_spec_P` and `fv_cover_P`, plus the sanity items at P = 8;
  - `eqy_rtl`, `seq_eq_P` (no lemmas by default) and `equiv_P`.
- `gate/eqy_rtl.eqy` uses strategy sat at depth 1, with ports and the registers `ring`, `S`, `L` matched by name. It is an unbounded proof from any common state.
  - The gold side is purged of internal names.
  - One merged partition: `ring`, `S` and `L` are each merged with `O0`. Separate partitions gave spurious "unknown" results on the netlist, and `merge *` segfaults Yosys 0.71.
  - A state re-encoding gives "unknown", so such a candidate must use `seq_eq`.

## 7. Assumptions and limitations

- **Formal assumptions: none.** The controller protocol is described (section 2) but never assumed.
- Formal is 2-state. X is checked only by Icarus on RTL (`edge_P`, `!==` after the flush). On gate netlists, Icarus 4-state X-pessimism keeps `L[11:8]` at X after the first-token load: an `xor2` gets an X input that is logically masked. The gate `edge_P` therefore uses Verilator 2-state with random power-up (2 seeds) on the Yosys view. The PDK UDP flop view mis-simulates under Verilator (one-cycle skew), so it is not used there. No formal X-propagation check is done.
- `fv_spec` constrains `O0(t)` for `t ≥ P` only. A pathological candidate whose `O0` in the first P−1 cycles after power-up depends on the current inputs (hidden power-up state) is not caught by `fv_spec` or `seq_eq`; `eqy_rtl` catches it only when the state names match. Such a candidate violates R14 (power-up behaviour) and must be rejected in review.
- `eqy_rtl` matches by name; a re-encoded state needs `seq_eq`, plus lemmas if its state is not visible within P edges.
- `edge_P` is sampled (D9b), not exhaustive. The edge vectors exercise the controller form, but the controller itself is out of scope.

## 8. Constraints for optimizers

- Keep R13 (ports and parameter), R14 (no reset, no init, plain positive-edge flops on `clk`) and R1–R12 at P = 2, 4 and 8.
- Off-protocol behaviour (R4, R9 with `accum_en`, R10 in score mode) is part of the contract. A candidate that changes it must bring a reviewed, protocol-restricted amendment.
- Clock gating is rejected, as for max_reg. Accept it only through a reviewed extension.

Reuse:
- `verif/run_all.sh --rtl <file> --out <dir> [--lemmas F]`
- `verif/run_all.sh --gate --rtl <netlist> --config <P> --out <dir>`
