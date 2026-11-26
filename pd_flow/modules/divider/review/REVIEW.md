# divider Phase 1: independent review of Agent 1's verification contract (Agent 2)

Scope: `pd_flow/modules/divider/verif/` at commit **`be7df42`**, unmodified (file hashes in
[`contract_hash_be7df42.txt`](contract_hash_be7df42.txt)). Requirements were derived first, before any
`verif/` file was read: [`EXPECTED.md`](EXPECTED.md). Golden: `snapshot/divider.v` (SHA-256 `a4943458…`).
Agent 2 used at most 2 jobs and never read `opt/`. Rules applied: D9/D9b.

## Verdict: **APPROVE**

There are no blocking findings.
- All **33 must-kill mutants** are killed by gating items: 23 RTL and 10 GF180 gate-level.
  - 31 are killed by a formal item (SBY or EQY), and 29 also by the edge/spot items.
  - The other 2 (default-parameter changes) are killed by the static `lint_11` default check. That is the correct mechanism.
- Of the **11 equivalent mutants**, 8 survive and pass the contract's own EQY items, which proves them equivalent.
  - The other 3 (e01, e05, m18) are behaviourally equivalent but are rejected by the strict items. They are conservative false kills, not gaps.
  - My independent reference proves all 3 correct (§4).
- The clean rerun from `git archive HEAD` reproduces every status of the committed evidence.
- My own formal reference, written independently, proves the golden correct in all four configurations.

The gate-mode `eqy_rtl` failure at config 11 that I found during the audit was a real fail-closed bug: the golden 11 netlist failed. Agent 1 fixed it before the commit, by matching `divisor`/`invalid`. I validated an alternative fix independently, and the committed fix passes on all three golden netlists. It is closed.

## 1. Reproduction

| Run | Result |
|---|---|
| `git archive be7df42` (verif, snapshot, python/src) into the scratchpad, golden RTL, `--jobs 2` | 22/22 gating ok, `all_ok = true`, 29 s. Every item status identical to `verif/results.json` ([`rerun/ga_rtl/`](rerun/ga_rtl/results.json)) |
| Same copy, gate `divider_00_gf180.v` (`--config 00`) | 12/12, identical to `gate/evidence/golden_00_gf180` |
| Same copy, gate `divider_11_gf180.v` (`--config 11`) | 11/11, identical to `gate/evidence/golden_11_gf180` |
| Same copy, gate `divider_00_clkbuf_gf180.v` | 12/12, identical to `gate/evidence/clkbuf_00` |
| Earlier rerun of the byte-identical working copy (only `SPEC.md` wording and `RTM.md` differ from `be7df42`) | 22/22, identical ([`rerun/clean_rtl/`](rerun/clean_rtl/results.json)) |
| My GF180 netlists (`gate_synth.sh`, a copy of `verif/gate/synth_gf180.sh`) | byte-identical to `verif/gate/netlists/divider_{00,11}_gf180.v` |

## 2. Independent reference (Agent 2, [`ref/`](ref/))

[`ref/div_spec.sv`](ref/div_spec.sv) is written from EXPECTED.md. It shares no code or algorithm with
`verif/formal/ref_divider_seq.v`.

**Value (non-restoring).** A radix-2 non-restoring divider runs in lockstep with a 0..24 protocol counter:
- the signed partial remainder stays in [-L, L);
- each quotient bit is (new remainder >= 0), and there is one final correction;
- it rounds up when 2R >= L, then applies `-(q+up)`;
- at CHECK = 1, the range is checked on its own quotient.

Agent 1's reference is a divisor-shifted long division, and the golden is a restoring division with the dividend shifted.

**Domain at 00.** It is stated as SBY **assumptions**:
- the multiplicative in-range condition `32|O| < 4095·L` (O >= 0) or `< 4097·L` (O < 0) at the accept edge;
- the denominator held while busy.

This is the opposite style to Agent 1, who conditions the assertion instead. It gives a cross-check of the domain.

**Proof aids.** White-box `inv_*` lemmas relate the golden's `quotient`/`remainder_value` to the non-restoring state, for example `R = r < 0 ? r + L : r`. They are asserted, never assumed. Probes are connected with `connect -set` after `flatten`.

| Check | Result |
|---|---|
| k-induction, depth 2, golden at 00, 11, 10, 01 | **proven** (all 4, 0–9 s) ([`ref/runs/golden_L*`](ref/runs/)) |
| Covers, depth 55 (tie ±, −2048, 2047, negative→0, L = 4095, back-to-back, invalid at 11) | all reached. `c_invalid` is unreachable at 00, as intended: the domain assumption excludes it |
| EDGE = 1: the **multiplicative bracket** `(2Q−1)L <= 32|O| < (2Q+1)L` on the golden's result, for a table of 96 operand pairs (EXPECTED E1–E7 and 40 seeded random pairs), BMC depth 27 | 00: bounded-pass in 6 s (`ref/runs/edge_L0C0`). 11: bounded-pass in 6 s on the previous harness revision. That log was overwritten, and the rerun on the final revision timed out at 400 s in z3 (`ref/runs/edge_L1C1`): **timed-out**. This check anchors the non-restoring reference to the definition without using a divide. Negative controls fail `e_bracket`: m03 and m17 at 00, and m03 at 11 (`ref/runs/negctl_*`) |
| All 30 RTL mutants through the reference (k = 2), [`ref/mutant_ref_results.txt`](ref/mutant_ref_results.txt) | Every equivalent mutant is PASS at 00 and 11. Every must-kill mutant fails a property at its relevant configuration (UNKNOWN: induction broken, or basecase FAIL). Out-of-context mutants PASS at the configuration where they are harmless (m13, m15 and m18 at 00) |

Things tried and not used as evidence: a black-box multiplicative bracket under k-induction, and a lemma-guided BMC at depth 30. With z3, the first was still open after more than 40 minutes and the second took more than 3 minutes per step. Agent 1 also reports that a black-box `a_comp` does not scale. White-box lemmas are therefore needed for an unbounded arithmetic proof of this datapath.

## 3. Audit (including the points Agent 1 flagged)

### 3.1 White-box `fv_result_*` and candidates without the names: adequate (no finding)

A candidate that lacks the lemma names reports `unsupported` (non-gating), but it cannot be accepted on that basis:
- `eqy_rtl_*` also matches registers by name, so the same candidate fails strict EQY, which is gating. Every path is fail-closed.
- A candidate that keeps the names but changes their meaning fails the lemmas, which are gating.
- A candidate that passes strict EQY is cycle-equivalent to the golden, for which `fv_result_*` is an unbounded proof. The arithmetic proof therefore transfers.

The `unsupported` → non-gating rule loses nothing as long as `eqy_rtl` stays gating and strict.

Gate netlists likewise rest on `eqy_rtl` (strict, unbounded) against the golden RTL, plus `edge_CC`. **This is adequate.** Skipping `fv_result` and the covers at gate level is fine: the covers are harness reachability already shown on the RTL.

### 3.2 Config 00: A1–A4 condition the assertion (no finding)

`spec_now = rvalid && !lbad && denominator == Lx`. Here `rvalid` is the reference's own validity: L ≠ 0, S ≠ −2^19, m ≤ 2047 or 2048. That is exactly the in-range domain.

- **Not over-constrained.**
  - All inputs are free, and every protocol property (R4–R11) is asserted for all inputs.
  - The domain is the exact rounded-in-range set, not the narrower chip set −128L ≤ O ≤ 127L.
  - A1 adds the accept edge to the 24 edges the golden actually reads. That is harmless, because the reference latches `Lx` on that edge, and the controller meets it.
- **Not vacuous.**
  - The covers `c_done_pos`, `c_done_neg`, `c_max`, `c_min` and `c_tie_neg` are all reached under `spec_p`, and `c_unspec` reaches `!spec_p`.
  - `fv_sanity_stab_00` shows that the stability condition matters.
- **Cross-check.** My reference assumes the domain, where Agent 1 conditions on it, and proves the same golden at 00. The two statements agree.
- **Observation (EXPECTED R2).** The in-range condition alone implies A2 and A3. L = 0 is never in range, and 32·524288 = 16,777,216 > 4097·4095. A2 and A3 are therefore redundant but harmless.

### 3.3 EQY setup (no finding; one strictness note → Agent 3 constraints)

- The golden's combinational names are excluded from matching, except `divisor` and `invalid`. At 11 these are the netlist names of the `saved_divisor` and `invalid_r` flops; at 00 they are an input alias and a constant 0.
- All partitions are merged, `dffunmap` runs on both sides, and the strategy is `sat` at depth 1.
- PASS is an unbounded strict equivalence over matched state. Unmatched state can only make it fail, never pass falsely.

During the audit (before `be7df42`), the 11 netlist failed `eqy_rtl` because those two flops carried the excluded alias names. I validated a fix (`gold-match g_divisor.saved_divisor divisor`, `gold-match invalid_r invalid`). It gives PASS with 16 names matched on golden 11, still PASS on golden 00, and FAIL on an 11 netlist with two `saved_divisor` D inputs swapped ([`formal_checks/fix_B1/`](formal_checks/fix_B1/)). The committed fix removes the two `gold-nomatch` lines instead. It is equivalent in effect, and my rerun shows it passes on all three golden netlists.

**Strictness.** EQY rejects behaviourally equivalent register-level rewrites:
- e01 latches `saved_divisor` only on start;
- e05 holds `step` in idle;
- m18 drops the L = 0 term of `invalid_r`, which `overflow` already covers.

All three are fail-closed. Each is proven correct by my reference. This is a constraint for Agent 3, not a defect.

### 3.4 Lint waiver (no finding)

The waiver covers `difference[12]` only. It is unused in the RTL: `subtract` uses `[13]` and the remainder uses `[11:0]`. The checker waives only UNUSEDSIGNAL on non-port signals. m21 and m22 show that the default-parameter check fails when it should, and its exit status is taken from the check itself (`|| r4=1`, no pipe).

### 3.5 Proof validity, labels, exit-status plumbing (no finding)

- **Proofs.** `fv_proto_*` (k-induction at depth 28, and abc pdr) and `fv_result_*` (k-induction at depth 3, with lemmas) are genuine unbounded proofs. The assert and cover counts are checked by `count_props.py`. The init guard runs before `flatten`.
- **Labels.** `not-proven` (SBY UNKNOWN) maps to `inconclusive` with `ok = false`.
- **Exit status.**
  - Every check's status is taken directly. The final `rc=${PIPESTATUS[0]}` takes the Python status, not the status of `tee`.
  - `vvp` uses `$finish_and_return(1)` on a mismatch or on zero points, and the point counts are cross-checked against `gen`.
- **Engine FAIL without a replay.** An engine FAIL that SBY could not replay is reported as `failed`.

### 3.6 Edge/spot blind spots (NB1, informational)

m16 corrupts one interior point (12345/678). It is killed only by `fv_result_*` and EQY, as expected: sampling cannot find rare points. The arithmetic is proven, so this is not a gap.

The edge set covers ties, near-ties, the 2046..2049 boundaries, int8 bounds, L ∈ {1 … 4095}, extremes and L = 0. Every edge-detectable mutant (m03–m06, m14, m17, m23) is killed by `edge_00` and `edge_11` as well.

### 3.7 Minor notes (non-blocking)

- **NB2.** X-freedom is checked only by Icarus `!==` at the sampled cycles. D9 asks for formal X-propagation. Both SPEC §7 and the RTM state this limit. The datapath registers are unreset by design but are reloaded in every IDLE cycle, and `fv_proto_*` proves power-up independence in 2-state.
- **NB3.** `refcheck` is labelled `pass-static`, but it is a sampled simulation of the reference against the model on 7,353 points, so `pass-sampled` would be more accurate. This is cosmetic.
- **NB4.** Cover runtime depends on load. The e02 covers took about 775 s under a load average of about 35, against `T_FV = 900`. A candidate run on a loaded machine can time out. That fails closed, but rerun before concluding anything.
- **NB5.** L ≥ 255 depends on a consistent tape: `cont = 1` before any fresh run can give L = 0. A1–A4 must be discharged by the controller-level contract, as SPEC §2 and the RTM already say.

## 4. Mutation testing (contract `be7df42`, unmodified, gating items only)

The drivers are `run_mutants.py` (the exp_lut driver; gate mutants take `--config` from the manifest), `make_mutants.py` and `make_gate_mutants.py`.
- RTL mutants ran on a hash-checked copy whose code files are byte-identical to `be7df42`.
- Gate mutants ran on the `git archive` copy.

Results are in [`mutation_results.json`](mutation_results.json), and the full table is in [`mutation_summary.md`](mutation_summary.md).

### Score

| Set | Must-kill | Killed | By a formal item | By edge/spot | Equivalent | Survived (EQY-proven) | Killed but behaviourally equivalent |
|---|---:|---:|---:|---:|---:|---:|---:|
| RTL | 23 | 23 | 21 | 20 | 7 | 4 (e02, e03, e04, e06) | 3 (e01, e05, m18) |
| Gate (GF180, config 00) | 10 | 10 | 10 | 9 | 4 | 4 (g03 buffer, g04 clkbuf, s_e02, s_e03) | 0 |
| **Total** | **33** | **33** | **31** | **29** | **11** | **8** | **3** |

- **Formal kills.** m21 and m22 (default `CHECK_INVALID` or `LATCH_DENOMINATOR` changed from 1 to 0) are killed by `lint_11` only. That is the correct static check, and it is what killed m34 in the exp_lut review.
- **Edge kills.** m16 and gate s_m16 (the rare point) are killed by formal items only.
- **Survivors.** All 8 survivors passed `eqy_rtl_00/11`, or `eqy_rtl` at gate level, inside the contract run itself. Those passes are the EQY equivalence proofs.
- **The 3 rejected equivalents** are proven correct against the specification by my reference:
  - e01 and e05 at 00 and 11;
  - m18 at 11, with the L = 0 term of my invalid lemma relaxed (`ref/runs/equiv_m18_11_relaxinv`). m15 under the same setting fails `a_value`.
- **Reclassification.** m18 was generated as out-of-context, and I reclassified it as equivalent. With L = 0 every restoring step subtracts, so the quotient is all ones and `overflow` forces 0.
- **g02.** The first version used the wrong output pin (`Z` instead of `ZN`) and was killed by lint for that reason. It was regenerated and rerun: it is killed by `edge_00` and `eqy_rtl`.

### Mutant list (classes)

**RTL functional bugs (00):**
- latency +1 / −1 (m01, m02);
- ties toward zero, and negative ties toward +inf (m03, m04);
- negative result off by one, and sign from bit 18 (m05, m06);
- shift rotates instead of zero-filling (m09);
- reset keeps `result`, reset keeps `done`, reset does not abort, start accepted during reset (m10, m11, m12, m24);
- remainder not cleared at load (m14);
- rare interior point, and lost rounding at L = 4095 (m16, m17);
- `done` sticky (m20);
- incrementer carry lost (m23).

**RTL out-of-context bugs (not exercised by the chip):**
- start while busy restarts (m07);
- shift beats completion (m08);
- LATCH = 1 samples continuously (m13);
- `CHECK_INVALID = 1` flags −2048 (m15);
- `busy` low in ROUND (m19);
- default parameters changed (m21, m22).

**Gate mutants:**
- g01: two `result` D inputs swapped;
- g02: xor2 replaced by xnor2 in the datapath;
- g05: `done` flop negative-edge (structural);
- g06: `busy` stuck at 0;
- mapped netlists of m01, m03, m05, m16, m17 and m23;
- equivalents: an output buffer (g03), a CTS clkbuf (g04), and mapped e02 and e03.

## 5. Exact changes

None are required. The only blocking defect found (the gate-11 EQY name match) was fixed in `be7df42`. Optional follow-ups for NB2/NB3:
- **NB2:** a formal X-propagation item, for example Yosys `sat -enable_undef -set-init-undef -set-def-inputs` over one reset and one division, with m14 as the negative control.
- **NB3:** relabel `refcheck` as `pass-sampled`.

## 6. Constraints for Agent 3

1. **Interface.**
   - Keep the ports, widths and directions exactly.
   - Keep both parameters, with defaults `LATCH_DENOMINATOR = 1, CHECK_INVALID = 1` (`lint_11` checks them). The chip uses 0/0.
2. **Cycle behaviour must be identical in both configurations.**
   - Completion is exactly 24 edges after accept, and `busy` covers exactly those 24 cycles.
   - `done` is a one-cycle registered pulse, with `busy = 0` while it is high.
   - Starts while busy are ignored, and an accept in the `done` cycle works.
   - `shift` works in every state, and a completion overrides a shift.
   - Reset is synchronous, active low and has priority. It sets `result = 0`, `done = 0` and idle, and aborts a division.
   - There is no initial value, and behaviour after the first reset must not depend on the power-up state.
3. **Value.**
   - `round(16·S/L)`, ties away from zero, no negative zero.
   - At 11, invalid requests give 0. At 00, behaviour only has to be correct under A1–A4.
   - The **strict EQY does not let you exploit A1–A4 or idle-cycle don't-cares.** Even behaviourally equivalent rewrites of what the registers hold while idle fail it (e01, e05, m18). Any such candidate needs a reviewed, domain-restricted or behavioural proof before it can be accepted.
4. **Register names.**
   - EQY matches registers by name. Keep `state`, `step`, `quotient`, `remainder_value`, `negative`, `result`, `done`, `g_divisor.saved_divisor` and `invalid_r`, or their netlist aliases `divisor`/`invalid` at 11.
   - `fv_result_*` additionally needs their golden meaning. Re-encoding the state, for example a one-hot FSM, a down-counter `step` or a different quotient layout, fails `eqy_rtl` and needs a reviewed match.
5. **Structure.**
   - Positive-edge D flops on `clk` only (buffers are allowed), with no async set or reset, latches, memories or `init`.
   - Clock gating needs the reviewed extension noted in the max_reg contract.
6. **LATCH_DENOMINATOR = 0** uses `denominator` live through the ROUND cycle. Do not add a latch at 00 unless it is shown to be equivalent. Strict EQY would reject an added register.
7. **Load.** Run candidates when the machine is quiet, or rerun on a `timed-out` result. Covers have taken up to about 775 s under load, against the 900 s limit.

## 7. Files

- [`EXPECTED.md`](EXPECTED.md): requirements written before reading `verif/`.
- [`ref/`](ref/): the independent formal reference. It contains:
  - `div_spec.sv` and `run_ref.sh`;
  - `edge_table.vh`;
  - `run_ref_mutants.sh` and `mutant_ref_results.txt`;
  - `runs/`.
- [`mutants/`](mutants/) and [`gate_mutants/`](gate_mutants/), each with a `MANIFEST.json`, plus the generators `make_mutants.py` and `make_gate_mutants.py`.
- [`run_mutants.py`](run_mutants.py), `mutation_runs/`, [`mutation_results.json`](mutation_results.json), [`mutation_summary.md`](mutation_summary.md), and `mutant_runs_{rtl,gate}.console.txt`.
- [`rerun/`](rerun/): the clean reruns (`ga_*` from `git archive be7df42`), [`rerun_git_archive.sh`](rerun_git_archive.sh) and [`rerun_clean.sh`](rerun_clean.sh).
- [`formal_checks/fix_B1/`](formal_checks/fix_B1/): validation of the gate-11 EQY match fix.
- Hashes: [`contract_hash_be7df42.txt`](contract_hash_be7df42.txt) and `contract_hash_at_audit.txt`.
- Superseded: `mutation_results_partial_pre_freeze.json` and `mutant_runs_rtl_partial_pre_freeze.console.txt`. These are 3 runs made while the contract was still changing. They are not evidence.
