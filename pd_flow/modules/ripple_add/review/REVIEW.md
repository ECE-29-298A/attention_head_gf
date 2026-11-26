# ripple_add: Phase 1 independent review (Agent 2)

All paths are relative to `pd_flow/modules/ripple_add/`, unless they start with `pd_flow/`.

## Verdict: **APPROVE**

Agent 1's contract (`verif/`) is correct, independent, unconstrained, honestly labelled,
and it killed every non-equivalent mutant (22/22). It did not kill any of the 3 equivalent
mutants. I found no blocking issues. The non-blocking findings below (N1 to N7) are
recommended improvements and need not be fixed before Phase 2. N3 should be fixed before
another phase reruns the contract with `--rtl`.

## Method

1. Before opening any of Agent 1's files, I wrote `review/EXPECTED.md` from the golden RTL
   and `mac_unit.v` only. It covers requirements E1 to E3 and contract items C1 to C8.
2. **Audit of `verif/`.** I read every file. I copied Agent 1's sources unchanged into
   `review/harness/verif_copy/`. Their hashes are in `review/harness/agent1_sources.sha256`,
   and after the review all 12 files still match. I did not edit or rerun anything in
   `verif/`, because `run_all.sh` writes its results in place (see N3).
3. **Clean rerun** on the golden RTL from a fresh copy: `review/rerun_golden/`
   (`results.json`, `run_all.out`, `logs/`). Result: 68/68 ok, `all_ok=true`, 24.8 s.
   Every item's status and detail string is identical to Agent 1's `verif/results.json`.
4. **Mutation testing.** `review/mutants/gen_mutants.py` generates 25 mutants from the golden
   file (descriptions in `mutants/mutants.json`). `review/run_mutation.sh` runs the
   unmodified contract on each mutant, each in its own fresh copy, with
   `run_all.sh --rtl <mutant>`. The output goes to `review/mutation_runs/<m>/` (results.json,
   logs, counterexample VCDs), and `review/summarize_mutation.py` writes
   `review/mutation_results.json`. The per-mutant `dut_sha256` in each results file matches
   the mutant file.
5. **Independent equivalence classification.** This check does not use Agent 1's harness.
   `review/equiv/miter.sv` with `miter.sby` compares the golden RTL against each mutant with
   no assumptions, `===`, and a stateless guard, at N = 12, 16 and 22
   (`equiv/equiv_summary.txt`). As a second engine, EQY with the SAT strategy runs at
   N = 12 and 22 (`equiv/eqy_template.eqy`, `run_eqy.sh`, `eqy_summary.txt`). The golden
   design checked against itself passes, and the m01 and m16 controls fail where expected.

## Mutation score

Score: **22/22 non-equivalent mutants killed (100%)**. 3/3 equivalent mutants survived, and
each is proven equivalent. There are no gaps. "Functional killers" lists the contract items
with `ok=false`, excluding cover, negative-control, build and lint fallout. A "–" in the
miter column marks the widths where the mutant is equal to the golden RTL.

| Mutant | Fault | Miter ≠ golden at | Functional killers | Static killers | Result |
|---|---|---|---|---|---|
| m01_sum_xor_to_or | `s=(a^b)\|c` | 12,16,22 | prove ×12, pdr ×2, exh ×12, vec ×5, rand ×4 | – | KILLED |
| m02_no_generate | carry drops `a&b` | 12,16,22 | prove ×11, pdr ×2, exh ×11, vec, rand | – | KILLED |
| m03_no_propagate | carry drops `c&(a^b)` | 12,16,22 | prove ×11, pdr ×2, exh ×11, vec, rand | – | KILLED |
| m04_carry_wrong_index | sum uses `c[i-1]` | 12,16,22 | prove ×11, pdr ×2, exh ×11, vec, rand | – | KILLED |
| m05_cin_ignored | `c[0]=0` | 12,16,22 | prove ×12, pdr ×2, exh ×12, vec, rand | lint ×8 (cin unused) | KILLED |
| m06_bit0_sum_no_cin | bit 0 sum drops cin (cin=1 only) | 12,16,22 | prove ×12, pdr ×2, exh ×12, vec, rand | – | KILLED |
| m07_msb_no_carry_in | MSB ignores carry | 12,16,22 | prove ×12, pdr ×2, exh ×12, vec, rand | – | KILLED |
| m08_loop_bound_short | `i<N-1`, s[N-1] undriven | 12,16,22 | prove ×12, pdr ×2, exh ×12, vec, rand | lint ×8 | KILLED |
| m09_stuck_at0_bit5 | s[5]=0 | 12,16,22 | prove ×7 (every proven N ≥ 6; N ≤ 5 has no bit 5), pdr ×2, exh ×7 (N=6..12), vec, rand | – | KILLED |
| m10_stuck_at1_msb | s[N-1]=1 | 12,16,22 | prove ×12, pdr ×2, exh ×12, vec, rand | – | KILLED |
| m11_b_bit_reversed | `b[N-1-i]` | 12,16,22 | prove ×11, pdr ×2, exh ×11, vec, rand | – | KILLED |
| m12_n22_only_bit20 | N=22 only | 22 | fv_prove_n22, fv_pdr_n22, vec_n22, rand_n22 | – | KILLED |
| m13_n12_only_msb | N=12 only | 12 | fv_prove_n12, fv_pdr_n12, exh_n12, vec_n12 | – | KILLED |
| m14_n22_only_cin1 | N=22 and cin=1 only (subtract MSB) | 22 | fv_prove_n22, fv_pdr_n22, vec_n22, rand_n22 | – | KILLED |
| m15_cin1_full_chain | cin=1 and a^b=all ones only | 12,16,22 | prove ×12, pdr ×2, exh ×12, vec, rand | – | KILLED |
| m16_rare_n22 | 1 input of 2^45, N=22 only | 22 | **fv_prove_n22, fv_pdr_n22 only** (vec_n22, rand_n22 pass) | lint ×8 (artefact, see note) | KILLED |
| m17_rare_all_n | 1 input per N, all N | 12,16,22 | prove ×12, pdr ×2, exh ×12 (vec and rand pass) | lint ×8 (artefact) | KILLED |
| m18_rare_n12_window | 1 input, N=12, b≥256 (outside mac_unit L range) | 12 | fv_prove_n12, fv_pdr_n12, exh_n12 (vec_n12 passes) | lint ×8 (artefact) | KILLED |
| m19_latch | `always @*` latch | – (SBY error: guard) | prove, pdr, cover: inconclusive (stateless guard) | lint (LATCH, state cell), build | KILLED |
| m20_default_n8 | default N 16→8 | – (equivalent at given N) | – | lint_ndefault (interface R5) | KILLED |
| m21_x_on_zero | s[0]=X at a=b=cin=0 | 12,16,22 | prove ×12, pdr ×2, vec_n12/n22 (Icarus `!==`); **exh/rand (2-state Verilator) pass** | – | KILLED |
| m22_comb_loop | redundant comb loop on c[0] | – (functionally equal) | – (formal proves it) | lint (Verilator UNOPTFLAT), build | KILLED |
| e01_carry_or | carry `c&(a\|b)` | none (SBY 12/16/22, EQY 12/22 PASS) | – | – | SURVIVED-EQUIVALENT |
| e02_carry_majority | carry = maj(a,b,c) | none (SBY, EQY PASS) | – | – | SURVIVED-EQUIVALENT |
| e03_behavioural | `s = a+b+cin` | none (SBY, EQY PASS) | – | – (lint clean, no waiver) | SURVIVED-EQUIVALENT |

Note on m16 to m18: their lint failures are an artefact of my mutant (unused localparams
KA/KB or KC/KD, giving `UNUSEDPARAM`). They are not evidence of contract strength. The
functional result is the one that matters. The rare N=22 fault was missed by the 216k
golden vectors and the 50 M random vectors, and was killed only by the formal proofs at
N=22. So the contract does not rely on sampling for the instantiated widths.

## Audit findings

| # | Severity | Finding | Evidence |
|---|---|---|---|
| A1 | ok | **Golden model independent and correct.** Python computes `(a+b+cin) % 2**N` with unbounded integers. The testbench reference is uint64 `(a+b+c)&MASK`, and the formal reference is the behavioural `{1'b0,a}+{1'b0,b}+cin` truncated to N bits. None of the three uses the RTL's gate equations. I spot-checked the known-answer tests by hand (for example `(22, 5, ~3, 1) → 2`, `(22, 3, ~5, 1) → 0x3FFFFE`, `(12, 4095, 255, 0) → 254`). The exhaustive checksum cross-checks the testbench reference against numpy. | `verif/model/golden_model.py`, `verif/sim/tb_ripple_add.cpp`, `verif/formal/ripple_add_props.sv` |
| A2 | ok | **Coverage against EXPECTED.md.** C1: proven at N=12 and N=22 by two engines, plus exhaustive simulation at N=12. C2: no assumptions. C3: covers and an assertion count. C4: directed corners, including the mac_unit `term`/`~term` and `{4'b0,W}` patterns. C5: lint, structure and the stateless guard. C6: N=1 to 12, 16, 32, 64 and the default. C7: `--rtl`. C8: labels. R4 (subtract) has a dedicated proven assertion, `a_sub`. Every requirement R1 to R8 maps to passing items in the RTM, and my rerun reproduced them all. | `verif/SPEC.md`, `verif/RTM.md`, `review/EXPECTED.md`, `review/rerun_golden/results.json` |
| A3 | ok | **No overconstraint.** The harness and `.sby` contain no `assume`, `restrict`, `anyconst`/`anyseq` or `initial`, and every input is a free port. The `chformal -assume -early` line in SBY's generated prep script is SBY's own and has no effect here. | `verif/formal/ripple_add_props.sv`, `verif/formal/runs/*/model/design_prep.ys` |
| A4 | ok | **The depth-1 "proven (unbounded)" argument is valid.** The model has no state, and the guard `select -assert-none t:$ff t:$dff* … t:$anyinit` enforces this. The guard demonstrably fires: m19 gives `inconclusive` and `ok=false`. Each step's assertions are therefore a function of free inputs only, so the step-0 basecase is a full SAT check over all 2^(3N+1) inputs. Independently, a passing basecase plus induction is sound k-induction for any design; statelessness is what guarantees that depth 1 is sufficient. `abc pdr` agrees at N=12 and 22. The proof holds per N value, as the spec states. | `verif/formal/ripple_add.sby`, `review/mutation_runs/m19_latch/logs/fv_prove_n22.log` |
| A5 | ok | **Results labelling is honest.** Random and vector simulation are labelled `pass-sampled`, never proven; exhaustive simulation is `pass-exhaustive`; tool errors are `inconclusive` with `ok=false`; the negative control must refute and leave a trace. `all_ok` is the conjunction of every item, and the exit status follows it. | `verif/run_all.sh`, `verif/results.json` |
| A6 | ok | **The contract is implementation-agnostic.** The three equivalent re-implementations all pass 68/68, including the behavioural adder, which is lint-clean without the waiver. | `review/mutation_runs/e0*/results.json` |
| N1 | non-blocking | **The loop check rests on Verilator alone.** SPEC R3 attributes "no combinational loops" partly to Yosys `check -assert`. For m22, which has a real comb loop through `s[N-1]`, Yosys returned `yosys_rc=0`, and all formal proofs passed, because the loop is functionally redundant and is optimised away. Only Verilator `UNOPTFLAT` (lint, then build failure) caught it. Recommendation: add an explicit loop check that does not depend on Verilator (for example a Yosys `scc` selection asserted empty on the unoptimised netlist), or correct the SPEC wording. | `review/mutation_runs/m22_comb_loop/logs/lint_n22.log`, `.../run_all.out` |
| N2 | non-blocking | **X handling.** SPEC puts 4-state behaviour out of scope, yet m21 (an X output on a directed corner) was still killed by formal at every N and by Icarus (`!==`). The 2-state Verilator exhaustive and random runs missed it. This is adequate. Recommendation: state in SPEC that X outputs are caught by formal and Icarus, and that Verilator results are 2-state. | `review/mutation_runs/m21_x_on_zero/logs/vec_n22.log`, `exh_n12.log` |
| N3 | non-blocking (fix before Phase 2 reuse) | **`run_all.sh` overwrites its own evidence.** It deletes and rewrites `verif/logs`, `verif/formal/runs` and `verif/results.json`. The SPEC says later phases run `run_all.sh --rtl <new>`, which would destroy the Phase 1 golden evidence. Recommendation: add `--out DIR`, defaulting to `verif/` only for the golden DUT. That is why this review ran everything in copies. | `verif/run_all.sh`, the lines `rm -rf "$LOGS" "$VERIF/formal/runs" "$VERIF/results.json"` |
| N4 | non-blocking | **Label vocabulary.** AGENT_CONTEXT prescribes the labels proven (unbounded), bounded-pass (depth k), failed, timed-out, unsupported and inconclusive. results.json also uses `pass-sampled`, `pass-exhaustive`, `covered`, `failed-as-expected`, `pass` and `pass-with-waiver`. These labels are defined in SPEC §5 and are honest. Recommendation: add a canonical-label field per item so the orchestrator can parse results uniformly. | `verif/SPEC.md` §5 |
| N5 | non-blocking | **Weak covers.** 9 of the 11 covers are predicates on inputs only (for example `x > a`, `cin && a==ONES && b==0`). With no assumptions they are reachable by construction, and only `c_no_overflow` and `c_msb_generate` reference `s`. Non-vacuity really rests on two facts: there are no assumptions, and `count_props.py` confirms 2 assertions exist. That argument holds. Recommendation: make the covers observe outputs, for example `full[N] && s==ONES` or `cin && s==0`. | `verif/formal/ripple_add_props.sv` |
| N6 | non-blocking (forward-looking) | **Gate-level reuse.** `--rtl` takes one self-contained file. A Phase 3 GF180 netlist would need cell models (`--lib`). The SBY stateless guard also omits Yosys gate-level state cells (`$_DFF_*`, `$_DFFE_*`, `$_SDFF*`, `$_DLATCH_*`, `$_SR_*`, `$_ALDFF*`), which `lint/check_interface.py` does list. Soundness is unaffected (see A4), but R3 would then rest only on the lint item. | `verif/formal/ripple_add.sby`, `verif/lint/check_interface.py` |
| N7 | non-blocking | **Name-specific lint waiver.** It is documented, and it already rejects other warnings, which helped kill m05, m08, m19 and m22. A future implementation that keeps a dropped carry under a different name will fail R8 until its own waiver is reviewed. This is intended. | `verif/lint/check_lint.py` |

## Changes required

None blocking. Recommended, in priority order:

1. **N3:** add `--out DIR` to `run_all.sh` so that runs on a non-golden DUT do not overwrite
   `verif/results.json`, `logs/` or `formal/runs/`.
2. **N1:** add a loop check independent of Verilator, or fix the SPEC R3 wording about
   Yosys `check`.
3. **N4:** add a canonical AGENT_CONTEXT label per item.
4. **N5:** add output-observing covers.
5. **N2, N6:** small SPEC clarifications (X handling; the gate-level guard list and cell
   library input for Phase 3).

## Reproduce

```bash
cd pd_flow/modules/ripple_add/review
python3 mutants/gen_mutants.py                       # regenerate the 25 mutants
SCRATCH=/tmp ./run_mutation.sh                       # contract on every mutant (~25 s each)
(cd equiv && for f in ../mutants/*.v; do echo "$(basename $f .v) $(./run_equiv.sh $f $PWD/out/$(basename $f .v) | tr '\n' ' ')"; done > equiv_summary.txt)
/usr/local/bin/python3 summarize_mutation.py         # writes mutation_results.json
```
