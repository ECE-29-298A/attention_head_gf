# exp_lut: Phase 1 gate (verification contract frozen)

Date: 2026-11-26. Verdict: **PASSED**. Contract hash `d01fc4b8eb4f0492` (SHA-256 prefix of
`CONTRACT.sha256`, 21 files). Built under D9/D9b:
- combinational logic: directed edge cases plus spot checks;
- sequential logic: formal;
- EQY against the golden is mandatory for candidates;
- no exhaustive simulation.

Evidence the orchestrator checked itself:
- **Golden RTL from a clean state:** all gating items ok (about 15 s). The gate r0, r1 and r1+clkbuf
  netlists are all ok (Agent 1, two identical runs).
- **Gating items:**
  - `edge_r0` and `edge_r1`: 105,418 points; Verilator plus Icarus 4-state; R3/R4/monotonicity
    targeted checks.
  - `fv_prove_r1` and `fv_pdr_r1`: **proven**, no assumptions.
  - `fv_cover_r1`: 10/10.
  - 3 sanity controls, all refuted.
  - `eqy_rtl_r0` and `eqy_rtl_r1`: proven.
  - Lint, interface and default-parameter checks.
- **Independent review** (Agent 2, `review/REVIEW.md`): 63 mutation runs. 52 of 53 must-kill
  mutants were killed, every one by a formal item (49 also by `edge_*`). The 10 equivalent
  rewrites survive and are EQY-proven equivalent.
  - The one survivor exposed **B1**: the default-parameter check took its exit status from `sed`.
  - The orchestrator applied the reviewer's tested fix. Golden: all ok. m34 (default 0) is now
    killed by `lint_r1`. Per the review, this turns the verdict into APPROVE.
  - NB3 (constant 0.4923) was also fixed.
- **Reviewer rulings:**
  - R4 (W = 0 for D >= 2^20, including D[21]) is kept.
  - The lint waiver on unused clk/rst_n at gate r0 is narrow and justified.
  - `proc -norom` is necessary.
  - The shared formal include matches an independently certified table.

Limitations:
- The combinational function is not proven by the harness; for a candidate, completeness rests on
  `eqy_rtl_r0`, which must stay gating. Mutant m37 is killed only there.
- X behaviour is checked at the edge and spot points only (Icarus 4-state). NB1 (a formal xprop
  item) is not added; EQY caught every X mutant tried.

Constraints for optimizers: `review/REVIEW.md` §6.
