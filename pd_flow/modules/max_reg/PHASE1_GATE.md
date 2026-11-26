# max_reg: Phase 1 gate (verification contract frozen)

Date: 2026-11-26. Verdict: **PASSED**. Contract hash: `6d7f5b5ff9a94fc9` (SHA-256 prefix of
`CONTRACT.sha256`, which hashes the 16 contract source files in `verif/`).

Evidence the orchestrator checked itself:
- Golden RTL, clean state: `verif/run_all.sh` exit 0, 17/17. Agent 1 reports two identical
  clean runs (`verif/evidence/stability_2runs.txt`).
- Gate level, after the amendments: the clock-buffer netlist g05 passes 19/19 (`fv_prove_step`,
  `fv_pdr_seq` and `eqy_rtl` proven). The unsigned-compare mutant `s_m03` is killed, 7/19
  (formal and `eqy_rtl` failed).
- Formal, with no assumptions and M free at power-up:
  - the one-step next state;
  - after a load, M equals the max of the accepted scores;
  - power-up independence.

  Each is **proven** by both k-induction (Z3) and abc pdr. 23 covers reached (depth 10). Two
  negative controls fail as required.
- Simulation: Verilator and Icarus vectors (558,544 cycles, 4-state on Icarus), plus 100 M
  controller-pattern cycles, 100 M unconstrained cycles, 268 M one-step checks over a reduced
  space, and 64 power-up values.
- Independent review (Agent 2, `review/REVIEW.md`): **APPROVE**. Mutation: 44 runs, 35/35
  must-kill killed (32 functional bugs, all killed by formal, 30 also by simulation). 3 survivors
  are EQY-proven equivalent (`>=`, `!(S_in <= M)`, mapped `>=`). The EQY negative controls fail.
- Amendments N1 to N3 and `eqy_rtl` were applied by Agent 1. A rerun of all 44 mutants gave
  43 unchanged verdicts; g05 (clock buffer, equivalent) now passes, as intended.

Scope rules and limitations:
- Flops must be positive-edge and clocked by `clk` after collapsing non-inverting buffers.
  **Clock gating is rejected**; the requirements for a reviewed extension are in SPEC §7.
- Formal and Verilator are 2-state; only Icarus checks X (SPEC §8).
- `eqy_rtl` matches by name; a state re-encoding needs its own reviewed match (SPEC §6).
- `eqy_rtl` cannot see clock polarity (s_m13 negedge passes it), so lint, the `.sby` guards and
  simulation catch that case.

Phase 2 lead (Agent 2): `>` → `>=` is EQY-proven equivalent and maps 272 µm² smaller at module
level (3,088.65 vs 3,360.85 µm²). Chip-level acceptance requires `ll_synth.sh`.

Reuse: `verif/run_all.sh --rtl <file> --out <dir>` for RTL, and
`verif/run_all.sh --gate --rtl <netlist> --out <dir>` for gate level.
