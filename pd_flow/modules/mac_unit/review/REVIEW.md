# mac_unit Phase 1: independent review of Agent 1's verification contract (Agent 2)

Scope: `pd_flow/modules/mac_unit/verif/` at commit **`037dffd`**, unmodified, run from `git archive HEAD`
(hashes in [`contract_hash_HEAD.txt`](contract_hash_HEAD.txt)). The requirements were written first, before any
`verif/` file was read: [`EXPECTED.md`](EXPECTED.md). Golden: `snapshot/mac_unit.v` (`221110a1…`) + `ripple_add.v`.
At most 2 jobs. `opt/` was never read. Rules: D9/D9b.

## Verdict: **CHANGES REQUIRED** (one blocking item, F1; the patch is tested and applies cleanly)

- **B1 (blocking).** Candidate [`attacks/x05b_powerup_flag_O0_consistent.v`](attacks/x05b_powerup_flag_O0_consistent.v) reaches **`all_ok = True`, 24/24** at HEAD.
  - It adds one no-init flop `pf <= 1`. While `pf == 0`, which only happens in the power-up cycle, it drives `O0 = head ^ W`, so O0 depends on an input in that cycle.
  - That violates the contract's own R14, which SPEC §7 says can only be caught in review.
  - Its traces stay inside the golden's set of free power-up behaviours, so there is no chip-level consequence. But the gate lets an R14 violation through, and the fix costs two lines.
- **Fix F1** (`lint/check_interface.py`): reject more than `20·P + 34` flop bits. This turns the review-only rule into a gating check, and it is sound (argument below).
- **Fix F2** (`gate/eqy_rtl.eqy`, recommended, in the same patch): init guard after `proc`. Without it, `equiv_P` passes through `eqy_rtl` for init mutants m16 and m17. The run still fails on `lint_P` and `fv_*` (inconclusive), so F2 is defence in depth, not a hole.
- With F1+F2 applied, the contract can be **APPROVED** with no further review. Every run listed under Exact fix was already made on the patched copy.

Everything else is sound:
- **40 of 40 must-kill mutants are killed** (24 RTL, 7 attacks, 9 gate-level). 39 of them are killed by a formal item; x07 (`$initstate`) is killed by lint and edge.
- **The 9 equivalent mutants survive.** `equiv` is proven inside each run, and my reference proves 8 of them (c_rename is checked by the contract's `seq_eq` only).
- **The golden rerun from `git archive` matches the committed evidence item for item.**
- **My independent reference proves the golden from any start state, at RTL and at gate level.**

## 1. Reproduction ([`rerun/`](rerun/), [`rerun_git_archive.sh`](rerun_git_archive.sh))

| Run (git archive `037dffd`, `--jobs 2`) | Result |
|---|---|
| golden RTL | 25/25 gating, `all_ok = true`. Every item's status and ok flag is identical to `verif/results.json` |
| gate `mac_unit_8_gf180.v` (`--config 8`), `mac_unit_2_gf180.v` (`--config 2`) | 13/13 and 10/10, `all_ok = true` |
| gate: my own GF180 netlist of the golden ([`gate_synth.sh`](gate_synth.sh), not byte-identical to Agent 1's) | 13/13, `all_ok = true` |

## 2. Independent reference ([`ref/`](ref/))

[`ref/mac_spec.sv`](ref/mac_spec.sv) is written from EXPECTED.md and shares no code with `verif/formal/ref_mac_next.v` or the golden:
- **Ring.** The ring is a circular buffer with a rotating head pointer, not a shift register.
- **Arithmetic.** The arithmetic is integer multiplication by a signed bit weight.
- **Full state correspondence.** The DUT's internal `ring` is connected with `connect -set`. The harness asserts the mapping `ring[k] == buf[(hp+k) mod 8]` together with `S` and `L`.
- **Start state.** The DUT starts free. Only the reference side is mapped onto it, with an `$initstate` assume, so the proof holds for every start state.

| Check | Result |
|---|---|
| k-induction (depth 4), golden RTL and golden GF180 netlist (liberty cell functions) | **PASS** (8 s / 7 s) |
| covers (fresh load −255·128, L update, pass-2 bit-7 with qi = −128, bypass) | all reached |
| guards: DUT `init`, DUT formal cells, latches / async flops | a test assume and the init mutants trip them (ERROR = fail-closed) |
| 29 RTL mutants + 11 gate mutants ([`ref/mutant_ref_results.txt`](ref/mutant_ref_results.txt), [`ref/gate_mutant_ref_results.txt`](ref/gate_mutant_ref_results.txt)) | every bug FAILS (the 3 power-up mutants and g06 ERROR on the guards); the 8 equivalents PASS |

The reference checks full port behaviour, including inputs the controller never drives, the same domain as `fv_spec`. Because of that, m09, m11 and m22 are correctly killed even though they are chip-equivalent (EXPECTED R6).

## 3. Audit

### 3.1 `fv_spec_P`: black-box, from any state (no finding; this is the backbone)
- **Strength.** The checks are `S(t+1) = f(S(t), in)`, `L(t+1) = g(L(t), in)` and `O0(t+P) = h(O0(t), in)`, with no assumptions. The DUT has no init, so every state is an initial state.
- **Completeness.** As SPEC 4.3 argues, this determines the whole port trace once `S(0)`, `L(0)` and `O0(0..P−1)` are fixed.
- **Kills.** Every functional and out-of-context RTL mutant fails it, and so does x06 (a power-up flag that changes S at the first edge).
- **Non-vacuous.** All 3 sanity controls are refuted, the expected assert counts are checked, and 18 covers are reached at each P.
- **The one gap is the first P cycles of O0.** This is B1, closed by F1:
  - Let a candidate pass `fv_spec`. Its states reached at `t ≥ P` must realise all 2^(20P+34) behaviourally distinct golden states: the golden can reach any state by loading S, by first-loading and then accumulating L, and by fresh-loading and then accumulating each slot.
  - So it needs at least `20P+34` state bits.
  - With at most `20P+34` bits, every encoding is one of those states, the power-up state included. That state's behaviour, O0 in the first P cycles included, is therefore a golden state's behaviour, and does not depend on the inputs.
- Tested: x05b fails `lint_P` (195 > 194), while the golden, c_rename, e01 and both gate netlists pass (§5).

### 3.2 `seq_eq`: flush anchoring (sound, non-vacuous; it cannot be exploited)
- **The observers are correct.** I checked the `fresh_*` update rules against the golden equations (EXPECTED R3–R5):
  - S: a load, a score-mode add to a fresh S, or `score_en` in accumulate mode from a fresh head or a first load;
  - L: `first`, or an add to a fresh L;
  - ring: the tail takes `load_o || fresh_ring[0]` in accumulate mode, and `fresh_ring[0]` while scoring.
  Each flag is set exactly when the golden's value is a function of the inputs alone.
- **Soundness for the chip.** `a_eq` compares each output only when it is fresh. The controller consumes S, L and O0 only after the matching flush (EXPECTED R6), so a `seq_eq` proof is sound for chip use.
- **Pre-flush behaviour is not covered by `seq_eq`.** It is pinned by `fv_spec`, which gates for every DUT, so `seq_eq` cannot be used to escape it. Two examples:
  - x06 gets `seq_eq` proven but is killed by `fv_spec`;
  - x05b is the one gap, closed by F1.
- **Not vacuous.**
  - `fv_sanity_seq_P` is refuted for all three P.
  - 59 of the 63 runs of the 21 behavioural RTL must-kill mutants (× P = 8, 4, 2) fail `seq_eq` with a counterexample.
  - The other 4, m08 and m09 at P = 4 and P = 8, are not-proven, which still counts as a fail. `fv_spec` refutes both at every P.
  - The power-up mutants and the assume mutant are inconclusive because of the guards.
- **Lemma path.** `fresh_*` on the whitelist is harmless. Lemmas are only asserted, and are used as induction hypotheses only after they have been proven. Reading an observer cannot weaken `a_eq`.
- **Lint attacks ([`lint_attacks/RESULTS.txt`](lint_attacks/RESULTS.txt), 19 variants):**
  - `<<=`, `>>=`, `=`, `++`, `$past`, `$initstate`, `s_eventually`, `|->`, `head_f`, `load_o`, `clk`, `fresh_s.x` and an appended `assume` are all rejected;
  - accepted, and harmless: `fresh_s <= 1'b1` (a comparison in expression context), `fresh_ring[cand.S[2:0]]` and `cond ? 1 : …` (pure reads), a comment-only `; assume`, and a missing `;`.

### 3.3 DUT read without `-formal` (complete H1 replacement)
- `` `ifdef FORMAL `` code is never compiled. With x01 (a renamed candidate with the rare bug, hidden by an `ifdef FORMAL` assume) the bug is visible, and `fv_spec` and `seq_eq` both fail.
- A plain `assume` without `ifdef` (x04) is still elaborated in `-sv` mode, but the F1-style guard `select -assert-none t:$assume …` in both `.sby` files makes every formal item inconclusive (fail-closed).
- `(* anyconst *)`, `(* anyseq *)` and `allconst` are covered by the same guard, and init values by the `a:init` guards.
- `$initstate` (x07) is not covered by the formal guards, and x07 passes `fv_spec`, `seq_eq` and `eqy`. Verilator and Icarus reject it, so the gating `lint_P` and `edge_P` kill it. Adding `t:$initstate` to the two guards is optional hardening (NB1).
- Redefining a harness or PDK module (ga1: a netlist-local `xnor2_4` that is really an xor) gives a re-definition error. `lint_8` fails and every `fv_*` is inconclusive.

### 3.4 EQY: merged partitions and `opt_clean -purge` (sound; one documentation correction)
- **The proof strategy is sound.** Registers are matched by name, then `sat` depth 1 with dffunmap gives an unbounded next-state equivalence over the matched state. A re-encoded candidate gives unknown, which is a fail (c_rename shows this).
- **The name exclusions are safe.** The gold-side purge and `gold-nomatch` only drop combinational names; registers and ports stay.
- **The merged partition is valid.** I ran it on the golden, 3 gate netlists, 5 RTL equivalents and 3 gate equivalents: all are proven, and every bug fails.
- **The SPEC/`.eqy` claim "so it also fixes the power-up behaviour" is false (NB2).**
  - x05, which differs from the golden whenever `pf` powers up 0, gets `eqy_rtl` **proven**: EQY ignores the power-up value of an unmatched constant-D flop.
  - m16 and m17 (init values) also get `eqy_rtl` proven, so before F2 `equiv_P` was ok for them.
  - In all of these cases `fv_spec` and/or `lint_P` still fail, so `all_ok` is false. Power-up is pinned by `fv_spec`, lint and the guards, never by `eqy_rtl`.
  - F2 makes `eqy_rtl` fail closed on init values. The guard must come after `proc`, because `initial` blocks only become `init` attributes in proc_init. I tested that a guard placed before `proc` does nothing.

### 3.5 Gate-level `edge` (Verilator, 2-state, random power-up): acceptable
- It is a sampled, non-formal item, which D9b allows. X-propagation is not a concern for a design with no reset, because `fv_spec` proves the netlist from every 2-state start state.
- It passes on all 3 golden netlists, kills 8 of the 9 gate bugs (ga1 fails earlier, at elaboration), and passes the 3 gate equivalents.
- The Icarus 4-state version that existed before the commit spuriously killed the gate equivalents (`precommit/`), and Agent 1's switch fixes that.

### 3.6 Exit status and labels (no finding)
- Every status is taken from the check itself, never through a pipe. ERROR, UNKNOWN and timeout map to inconclusive, not-proven and timed-out, all with `ok = false`.
- Crashed jobs are added as inconclusive. A missing constituent fails `equiv`.
- `--rtl` cannot overwrite `verif/`.
- Labels follow the AGENT_CONTEXT mapping. As in the divider review, `covered` maps to `bounded-pass` and `edge` to `pass-sampled`.

## 4. Mutation testing ([`mutation_results.json`](mutation_results.json); console: `mutant_runs_{rtl,attacks,gate}.console.txt`)

Every mutant was run through the unmodified contract from `git archive 037dffd`, by [`run_mutants.py`](run_mutants.py). The generators are [`make_mutants.py`](make_mutants.py), [`make_attacks.py`](make_attacks.py) and [`make_gate_mutants.py`](make_gate_mutants.py).

| Set | Must-kill | Killed | By a formal item | Equivalent | Survived (equiv proven in-run) |
|---|---:|---:|---:|---:|---:|
| RTL (m01–m24) | 24 | 24 | 24 | 5 (e01–e05) | 5 |
| Attacks (x01–x07) | 7 | 7 | 6 (x07: lint + edge) | 2 (c_rename; x05b, power-up-equivalent) | 2 |
| Gate, GF180 at P = 8 (g01–g06, 4 mapped RTL bugs, ga1) | 9 | 9 | 9 | 3 (g04 buffer, g05 clkbuf, s_e01) | 3 |
| **Total** | **40** | **40** | **39** | **10** | **10** |

**RTL must-kill mutants (24):**
- sign and bit-7 errors (m01, m02, m03);
- W sign-extended, qi zero-extended (m04, m05);
- wrong `first` load: every bit, or without `accum_en` (m06, m07);
- ring bypass removed while scoring (m08), or selected by `accum_en` (m09, out of context);
- L condition: every component, bit 7, no `first` clear (m10, m11, m12);
- shift amount from `bit_sel[1:0]` (m13);
- rare values: W = 0xA5 at b = 3, qi = −128 (m14, m15);
- power-up: init on everything, init on L, a POR flop that clears (m16, m17, m18);
- priority and S loads (m19, m20), `accum_en` ignored (m21), O0 zero-extended (m22, out of context), ring reversed (m23), ring stalled while scoring (m24).

**Survivors:**
- **e01–e05:** rewrites with `+`, `−` and wider operands, and the L condition written bitwise.
- **c_rename:** ring renamed. `eqy` fails and `seq_eq` is proven.
- **g04, g05, s_e01:** both `eqy` and `seq_eq` are proven, and my reference also passes.
- **x05b:** the B1 gap. With F1 it is killed by `lint_P`.

## 5. Exact fix (patch [`fix/F1_F2.patch`](fix/F1_F2.patch); `git apply --directory=pd_flow/modules/mac_unit pd_flow/modules/mac_unit/review/fix/F1_F2.patch`)

- **F1 (blocking), `lint/check_interface.py`, after the `nbits == 0` check:**
  `if nbits > 20 * P + 34: errors.append(f"{nbits} flop bits > {20 * P + 34} (golden ring + S + L): extra (hidden power-up) state")`
- **F2 (recommended), `gate/eqy_rtl.eqy` `[gate]`:** put `select -assert-none a:init` right after `proc; flatten; opt_clean`.
- **SPEC edits (text only):**
  - §4.3 and §7: the first-P-cycles gap is now closed by F1 (the counting argument in §3.1 above);
  - §6 and the `.eqy` header: `eqy_rtl` does not pin power-up behaviour (NB2).

Tested on a copy of `git archive HEAD` with the patch applied ([`fix/test_fixes.sh`](fix/test_fixes.sh), [`fix/test_fixes.console.txt`](fix/test_fixes.console.txt), `fix/runs/`):

| DUT | Result with F1 + F2 |
|---|---|
| golden RTL | 25/25, `all_ok = True` |
| gate 8 and gate 2 netlists | 13/13 and 10/10, `all_ok = True` (194 and 74 flop bits) |
| c_rename, e01 | 24/24, `all_ok = True` |
| x05b | `lint_2/4/8` failed (195 > 194, 115 > 114, 75 > 74), `all_ok = False` |
| m16, m17 | `eqy_rtl_*` inconclusive (F2), `equiv_*` failed, `all_ok = False` |
| x07 | still killed by `lint` and `edge` |

**Non-blocking:**
- **NB1.** Add `t:$initstate` to the formal-cell guards in `mac.sby` and `seq_eq.sby`.
- **NB2.** The documentation correction above.

## 6. Constraints for Agent 3

1. **Interface.** Ports, widths and directions stay exact. Keep parameter `OUTPUTS`, default 8. Candidates must be correct at P = 8, 4 and 2: RTL runs all three, and gate level runs the configuration it is given.
2. **There is no reset and no power-up behaviour to change.**
   - No reset, no init, no `initial`, no clear-on-power-up logic, and no formal-only constructs: no `assume`, `assert`, `cover`, `` `ifdef FORMAL ``, `$initstate` or `(* anyconst *)`.
   - Behaviour from **every** start state must be the golden's.
3. **State budget.** At most `20·P + 34` flop bits (194 at P = 8): ring, S and L, with no extra state. This is F1, and it is also a lower bound, so the count must be exact. Retiming that adds flops, or a power-up flag, is rejected.
4. **Full port behaviour is contract, not only the controller's domain.** `fv_spec` checks every input combination, including:
   - `accum_en` while `!accum_mode` (ring bypass, but L still updates);
   - `score_en` in accumulate mode (S takes the accumulate sum, 22-bit, with O0 sign-extended);
   - the L update at `sel == 0 && bit_sel == 0` regardless of mode.
   Changes that are chip-equivalent but differ at the port (m09, m11, m22) are killed. They need a reviewed, protocol-restricted amendment.
5. **The ring must turn every clock in both modes.** The head is updated only in accumulate mode, and the head is the low 20 bits.
6. **Equivalence routes.**
   - With the golden's register names (`ring`, `S`, `L`), `eqy_rtl` works.
   - A re-encoded or renamed state needs `seq_eq`, optionally with a lemma file of pure `assert property` expressions over `gold.*`, `cand.*` and `fresh_*`.
   - Either way, `fv_spec_P` and `lint_P` must pass. `eqy_rtl` alone proves nothing about power-up.
7. **Structure.**
   - Positive-edge D flops on `clk` only (buffers are allowed), with no latches, memories or async or sync reset or set.
   - No netlist-local cell definitions.
   - Clock gating is rejected, as for max_reg.

## 7. Files

- **Requirements and reference:**
  - [`EXPECTED.md`](EXPECTED.md);
  - [`ref/`](ref/): `mac_spec.sv`, `run_ref.sh` (`GATE=1` for netlists) and `runs/`.
- **Mutant sources:**
  - [`mutants/`](mutants/), [`attacks/`](attacks/), [`attacks2/`](attacks2/), [`gate_mutants/`](gate_mutants/) and [`gate_attacks/`](gate_attacks/), each with a `MANIFEST.json`;
  - [`gate_netlists/golden.v`](gate_netlists/golden.v).
- **Mutation runs:**
  - `mutation_runs/` (per-run `results.json` and logs);
  - [`mutation_results.json`](mutation_results.json): per-run kills, the summary, and the `agent2_ref` verdict for each mutant;
  - `mutant_runs_*.console.txt`.
- **Reruns and fixes:**
  - [`rerun/`](rerun/) and [`rerun_git_archive.sh`](rerun_git_archive.sh);
  - [`fix/`](fix/): `F1_F2.patch`, the patched files, `test_fixes.sh` and `runs/`;
  - [`lint_attacks/`](lint_attacks/).
- **Hashes:** [`contract_hash_HEAD.txt`](contract_hash_HEAD.txt) (commit `037dffd`) and `contract_hash_at_audit.txt` (the pre-commit working copy, which differs only in gate-mode `edge`).
- **Superseded:** `precommit/`, the runs against the pre-commit working copy. Its gate equivalents were spuriously killed by the old Icarus gate edge. It is not evidence.

**CHANGES REQUIRED.** Apply `fix/F1_F2.patch`, at minimum F1. Once it is applied the contract is approved: every patched run above is already done.
