# ripple_add: Phase 1 gate (verification contract frozen)

Date: 2026-11-26. Verdict: **PASSED**. Contract hash: `b879560878477abf` (SHA-256 prefix of
`CONTRACT.sha256`, which hashes the 17 contract source files in `verif/`).

Evidence the orchestrator checked itself (not taken from agent claims):
- Golden RTL, clean state: `verif/run_all.sh` exit 0, 68/68 ok. The first rerun exposed an SBY
  status-db race (2 items crashed); it was fixed and confirmed stable over 5 runs by Agent 1 and
  over 2 further orchestrator reruns.
- Formal: `s == a+b+cin mod 2^N` and the subtract form `a + ~x + 1 == a - x`, **proven**
  (stateless, depth-1, complete) for N = 1,2,3,4,5,7,8,12,16,22,32,64 with smtbmc/Z3, and with
  abc pdr at N = 12, 22. 16 covers reached, including 5 on the output. The negative control fails as expected.
- Simulation: N <= 12 exhaustive (N=12: 2^25 inputs, checksum against the model); N=22: 216,556
  golden vectors on Verilator and Icarus, plus 50 M random.
- Gate level (GF180 7-track netlists from the synth_area recipe): N=22 10/10, N=12 11/11 (proven;
  N=12 exhaustive). This mode is used to check Phase 2 and 3 netlists.
- Independent review (Agent 2, `review/REVIEW.md`): **APPROVE**. Mutation: 22/22 non-equivalent
  mutants killed; 3 equivalent survivors proven equivalent (SBY miter and EQY). A rare-input
  N=22 mutant (1 of 2^45 inputs) is killed only by formal. All 25 verdicts were unchanged after
  the hardening pass. The loop mutant m22 is now also killed by the Yosys structural check.

Documented limitations:
- X/4-state behaviour: only Icarus is 4-state; Verilator is 2-state (SPEC section 7).
- Formal and simulation cover N <= 64 (the design uses 12 and 22).
- `pass-static` labels static checks (lint, structure, interface, build); it is not a proof.
- Gate mode: `cells_prep` reports pass on a file with no modules (seen when a non-Verilog file was
  passed). The run still fails overall because the later checks fail, so this is not a false pass.

Reuse in Phase 2/3: `verif/run_all.sh --rtl <file> --out <dir>` for RTL, or
`--rtl <netlist> --gate <N> --out <dir>` for gate level. `verif/` holds the frozen golden evidence.
