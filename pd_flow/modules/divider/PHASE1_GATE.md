# divider: Phase 1 gate (verification contract frozen)

Date: 2026-11-26. Verdict: **PASSED**. Contract hash `549f089fd92465c1` (SHA-256 prefix of
`CONTRACT.sha256`, 25 files). Built under D9/D9b:
- sequential logic: formal;
- combinational arithmetic: edge cases plus spot checks;
- equivalence against the golden: mandatory.

The contract covers configuration 00 (`LATCH_DENOMINATOR=0, CHECK_INVALID=0`, shipped) and 11 (the
defaults).

History:
- `be7df42`: Agent 1 contract, 22 items.
- `083ce4d`: Agent 2 **APPROVE**.
  - 33/33 must-kill mutants killed by gating items, 31 of them by formal items.
  - Every survivor is EQY-proven equivalent.
  - Agent 2's independent non-restoring reference proves the golden at 00/11/10/01.
- `b2623b1`: amendment A-1, `seq_eq`. A reset-anchored sequential miter with candidate lemmas that
  are proven, never assumed. The gating rule becomes `equiv = eqy_rtl OR seq_eq`.
- Agent 2 review of A-1: CHANGES REQUIRED, two soundness holes, each with a tested fix.
  - **H1:** a candidate-side `` `ifdef FORMAL `` assume constrained the miter. Fix F1: a `seq_eq.sby`
    guard that allows no formal cell except assertions.
  - **H2:** a side-effecting lemma (`>>=`) made the output comparison vacuous. Fix F2: a token
    whitelist in `lemma_prep.py`.
  - The orchestrator applied the reviewer's patch unchanged and verified it.
    - x03 (H1) is now inconclusive, so it fails.
    - x04 with the `>>=` attack is rejected by `lemma_lint`.
    - The golden is 25/25, and `c_rename` with lemmas is 23/23.
  - Per the review, this turns the verdict into APPROVE.

Evidence the orchestrator checked itself, from a clean state, with the frozen contract:
- golden RTL: 25/25 gating;
- c06: RTL 23/23; contract-recipe gate netlists 00: 14/14 and 11: 13/13.

Assumptions at 00 (A1–A4) condition the result assertion; they are not assumed. The
controller-level contract must discharge them:
- A1: denominator stable during a division.
- A2: L >= 1.
- A3: S != -524288.
- A4: the rounded result is in range.

Limitations:
- X behaviour is checked by sampled Icarus simulation only, not by a formal X-propagation check.
- `fv_result_*` is white-box and gates only on the golden. A candidate's result correctness follows
  from `seq_eq` (or `eqy_rtl`) plus the golden's unbounded `fv_result` proof.
- Cover run time depends on load: up to about 775 s, against a 900 s timeout.
- Non-blocking from the review: add the F1 guard to `divider.sby` too; state in SPEC that the
  no-assume rule also covers candidate sources.

Constraints for optimizers: `review/REVIEW.md` §6 and §8.
