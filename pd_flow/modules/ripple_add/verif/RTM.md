# ripple_add: requirements traceability matrix

Requirements are defined in `SPEC.md` §3. Item IDs are the `id` fields in `results.json`;
logs are `logs/<id>.log`, SBY work dirs (status, engine logs, cover/counterexample traces)
are `formal/runs/ripple_add_<task>/`. All paths are relative to this directory.
Regenerate everything with `./run_all.sh`. A new implementation is checked with
`./run_all.sh --rtl FILE --out DIR` (RTL) or `--rtl NETLIST --gate N --out DIR` (gate level);
those runs never write here. The `label` column of `results.json` gives the standard label (SPEC §5).

| Req | Requirement (short) | Evidence (results.json item IDs) | Method | Expected status |
|---|---|---|---|---|
| R1 | `s == (a + b + cin) mod 2^N`, all inputs | `fv_prove_n{1,2,3,4,5,7,8,12,16,22,32,64}` (assert `a_sum`); `fv_pdr_n12`, `fv_pdr_n22` | SBY prove, smtbmc/Z3 and abc pdr | proven |
| | | `exh_n1` … `exh_n12` | exhaustive Verilator + model checksum | pass-exhaustive |
| | | `vec_n12`, `vec_n22` (Verilator + Icarus), `vec_n16`, `vec_n32`, `vec_n64` | golden-model directed + random vectors | pass-sampled |
| | | `rand_n16`, `rand_n22`, `rand_n32`, `rand_n64` | random, in-TB reference | pass-sampled |
| | | `selftest` (golden model known-answer tests) | model self-check | pass |
| R2 | wrap on overflow, carry out dropped | same proofs as R1 (`a_sum` compares the low N bits of the (N+1)-bit sum); covers `c_overflow_wrap`, `c_cin_a_ones`, `c_max_inputs`, `c_msb_generate`, and the output-observing `c_s_zero_wrap`, `c_s_ones_wrap`, `c_s_chain_n`, `c_s_msb_by_carry` in `fv_cover_n{1,4,8,12,22,32}`; directed wrap vectors in `vec_*`; port list in `lint_*` (no carry-out port) | proof + cover + sim + static | proven / covered |
| R3 | purely combinational, no state, no loops / undriven / multi-driven nets, no black boxes | `lint_n{default,1,8,12,16,22,32,64}`: Yosys on the unoptimised netlist (`proc -noopt; flatten`) runs `check -assert` (logic loops, undriven, multiple drivers) and `scc` asserted empty; zero word-level and gate-level state cells asserted twice (Yosys `select -assert-none` and `lint/check_interface.py`); no non-primitive cells after flatten. Verilator `UNOPTFLAT` is a second loop check. The SBY script also asserts a stateless model (word- and gate-level types) in every `fv_*` run | static structure check | pass-with-waiver (waiver concerns R8 only) |
| R4 | `b = ~x, cin = 1` gives `a - x mod 2^N` | `fv_prove_n*`, `fv_pdr_n*` (assert `a_sub`, second instance); covers `c_sub_borrow`, `c_sub_zero`, `c_s_sub_minus1`; subtract and mac_unit `~term` vectors in `vec_n22`; model `selftest` | proof + cover + sim | proven |
| R5 | ports `a`, `b` [N-1:0] in, `cin` in, `s` [N-1:0] out; default N = 16 | `lint_n*` (`lint/check_interface.py` on Yosys JSON; `lint_ndefault` checks the default width 16) | static interface check | pass-with-waiver |
| R6 | instantiated N = 22 and N = 12 meet R1 to R5 | N = 22: `fv_prove_n22`, `fv_pdr_n22`, `fv_cover_n22`, `vec_n22`, `rand_n22`, `lint_n22`, `fv_sanity_n22`. N = 12: `fv_prove_n12`, `fv_pdr_n12`, `fv_cover_n12`, `exh_n12` (all 2^25 inputs), `vec_n12`, `lint_n12`, `fv_sanity_n12` | all methods | proven + pass-exhaustive (N = 12) |
| R7 | generic N stays correct | `fv_prove_n{1,2,3,4,5,7,8,16,32,64}`, `exh_n1` … `exh_n11`, `vec_n16/32/64`, `rand_n16/32/64`, `lint_n{1,8,16,32,64}`, `fv_cover_n{1,4,8,32}` | proof + sim + static | proven |
| R8 | lint clean (one documented waiver) | `lint_n*` (Verilator `-Wall`, classified by `lint/check_lint.py`: only `UNUSEDSIGNAL 'c'[N]` waived) | lint | pass-with-waiver |
| — | checker sanity (flow detects a wrong reference) | `fv_sanity_n12`, `fv_sanity_n22` (assert `s == a + b` must fail; trace in `formal/runs/ripple_add_sanity_n*/engine_0/trace.vcd`) | negative control | failed-as-expected |
| — | proof is not vacuous | `fv_prove_*` detail `asserts=2` (property cells counted in the SBY model by `formal/count_props.py`); `fv_cover_*` detail `covers=16 reached=16 unreached=0`, 7 of them on the outputs; no assumptions in the harness | cover + model inspection | covered |
| — | gate-level reuse (Phase 2/3) | `gate/evidence/n22/results.json`, `gate/evidence/n12/results.json`: GF180-mapped golden netlists (`gate/netlists/`) run with `--gate N` | all methods at that N | all_ok |

Build items `build_n*` (Verilator model compile per N) are infrastructure, not requirement
evidence; a failed build makes the dependent `exh_*`, `vec_*`, `rand_*` items fail.

## Coverage gaps (stated limits)

- Formal proofs are per parameter value (12 values of N); no proof for all N symbolically.
- N > 64 is not simulated (64-bit testbench words) and not proven; it is not used.
- The negative control checks the formal flow only. DUT mutation testing is assigned to the
  independent verifier (Agent 2).
- 4-state (X/Z) input behaviour is not specified or checked. X outputs: see SPEC §7 (Icarus and
  formal see them; Verilator results are 2-state).
