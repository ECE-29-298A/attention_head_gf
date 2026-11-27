# mac_unit: Phase 1 gate (verification contract frozen)

Date: 2026-11-26. Verdict: **PASSED**. Contract hash `0ada467d86d5ee15` (SHA-256 prefix of `CONTRACT.sha256`).
It covers OUTPUTS 8 (shipped), 4 and 2, under D9/D9b.

**History:**
- `037dffd`: Agent 1 contract.
  - `fv_spec` proves the next-state equations from **any** start state (mac_unit has no reset).
  - `seq_eq` is anchored on the flush: `fresh_*` observers, lemmas asserted only, divider fixes F1/F2 kept, and the
    DUT read without `-formal`.
  - `equiv = eqy_rtl OR seq_eq`.
- Agent 2 review: CHANGES REQUIRED, **B1**. A hidden power-up flag (x05b) that changed O0 only in the power-up
  cycle passed 24/24. The reviewer's patch `review/fix/F1_F2.patch` was applied unchanged by the orchestrator:
  - **F1:** the flop-bit count must be at most 20·P+34; that count is exact and minimal for the golden.
  - **F2:** `select -assert-none a:init` in the gate `eqy_rtl`.
- After the patch, verified by the orchestrator:
  - golden 25/25, golden gate (8) 13/13;
  - x05b killed by `lint_P`;
  - c09 RTL 24/24, gate 13/13.
- Per the review, this turns the verdict into APPROVE.

**Mutation results** (HEAD contract): 40/40 must-kill killed, 39 of them by formal items. All 9 equivalents
survive with equivalence proven. The independent reference (circular buffer plus head pointer) proves the golden
from any state at RTL and gate level.

**Limitations:**
- X behaviour is checked by sampling only.
- `$initstate` is not covered by the formal guards; lint and edge kill it.
- Off-protocol port behaviour is part of the contract.

Constraints for optimizers: `review/REVIEW.md` §6.
