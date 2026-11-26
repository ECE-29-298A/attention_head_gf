# divider: requirements traceability matrix

Requirements are defined in `SPEC.md` §3 and the caller guarantees A1–A4 in §2. Item IDs are
the `id` fields in `results.json`. Logs are `logs/<id>.log`; SBY and EQY work dirs are
`formal/runs/divider_<task>/` and `formal/runs/eqy_rtl*/` (both git-ignored). Regenerate
everything with `./run_all.sh`. A new implementation is checked with
`./run_all.sh --rtl FILE --out DIR` (RTL, configurations 00 and 11) or with
`--gate --rtl NETLIST --config CC --out DIR` (gate level, one configuration). Those runs never
write here.

Evidence kinds (D9b, SPEC §4):
- **proof**: SBY k-induction and abc pdr (`proven`);
- **EQY**: equivalence with the golden (`proven`);
- **edge/spot**: directed edge cases plus 4,000 fixed-seed spot checks through the DUT, Icarus
  4-state (`pass-sampled`);
- **cover**: `bounded-pass`, depth 30;
- **static**: lint, structure, interface, model (`pass-static`).

There is no exhaustive simulation. Every item is gating.

| Req | Requirement (short) | Gating evidence (item IDs; assertion / class names) | Kind | Expected status |
|---|---|---|---|---|
| R1 | result = round(16·S/L) at completion (00: under A1–A4) | `fv_result_00`, `fv_result_11` (`a_comp` against `ref_divider_seq.v`; all S, L, both configs); `refcheck` (reference = exact-integer model on 7,353 points); `edge_00` (6,066 points), `edge_11` (7,353); `eqy_rtl_00/11`; covers `c_done_pos`, `c_done_neg` | proof + edge/spot + EQY | proven, pass-sampled |
| R2 | ties away from zero, both signs | `fv_result_*` (`a_comp`); `fv_sanity_round_00/11` (truncating reference refuted); `edge_*` classes `tie` (162), `near_tie` (2,645); `selftest` (1,758 ties); cover `c_tie_neg` | proof + edge/spot | proven, pass-sampled |
| R3 | validity and range; 2047 / −2048 reachable, 2048 / −2049 invalid | `fv_result_11` (`a_comp`: invalid → 0); `fv_result_00` (out of range = outside the domain, unspecified); `edge_*` class `range` (m = 2046..2049 ±1, both signs, 14 L), `extreme`, `int8`; covers `c_max`, `c_min` | proof + edge/spot | proven, pass-sampled |
| R4 | latency 24 edges, data-independent; accept in the done cycle | `fv_proto_00/11`, `fv_pdr_proto_00/11` (`a_busy`, `a_done` against `cnt`); `fv_sanity_lat_11` (latency 23 refuted); `edge_*` (every cycle; 2,629/3,186 back-to-back); cover `c_b2b` | proof | proven |
| R5 | busy for 24 cycles, done one cycle, busy = 0 when done | `fv_proto_*`, `fv_pdr_proto_*` (`a_busy`, `a_done`); `edge_*` (checked after both clock edges) | proof | proven |
| R6 | starts while busy are ignored | `fv_proto_*` (the latency is unaffected), `fv_result_*` (the operands are unaffected: the reference is latched only at `cnt = 0`); `edge_*` (5,223 / 6,364 busy starts); cover `c_start_busy` | proof | proven |
| R7 | operand sampling (sum_in at accept; 11: denominator at accept; 00: A1) | `fv_result_*` (`sum_in` and, at 11, `denominator` are free after the accept); `fv_sanity_stab_00` (a moving denominator at 00 changes the result, so A1 is needed); `edge_*` (random `sum_in` during busy; random `denominator` at 11) | proof + edge/spot | proven |
| R8 | hold; registered outputs | `fv_proto_*`, `fv_pdr_proto_*` (`a_hold`, from the observed result); cover `c_hold`; `edge_*` (rise and fall checks) | proof | proven |
| R9 | shift in any state; serial MSB first | `fv_proto_*` (`a_shift`); cover `c_shift_busy`; `edge_*` (14,088 / 17,047 busy shifts; 606 / 735 12-bit serial shift-outs checked bit by bit) | proof + edge/spot | proven |
| R10 | completion overrides shift | `fv_result_*` (`a_comp` applies whatever `shift` is); `a_shift`/`a_hold` exclude only the completion edge; cover `c_shift_done`; `edge_*` (1,011 / 1,226 completion-edge shifts) | proof | proven |
| R11 | synchronous reset; abort | `fv_proto_*` (`a_rst`); cover `c_abort`; `edge_*` (210 / 254 aborts with start = shift = 1) | proof | proven |
| R12 | CHECK_INVALID = 1: invalid → 0 at normal latency | `fv_result_11` (`a_comp`, reference value 0); covers `c_invalid`, `c_lzero`; `edge_11` classes `l_zero`, `extreme`, `range` and `spot_full` | proof + edge/spot | proven |
| R13 | power-up: no initial value; behaviour after the first reset independent of it | every `fv_*` proof (DUT state free; asserted from the first reset edge); `fv_sanity_pu_00` (power-up ≠ reset state, refuted); covers `c_pu_busy`, `c_pu_result`; `.sby` init guard before `flatten`; `lint_*` (no `init`) | proof + static | proven |
| R14 | ports; 2 parameters, defaults 1/1 | `lint_00`, `lint_11` (`check_interface.py --params`); `lint_11` also elaborates without parameters and requires 1/1 (exit status from the check, B1) | static | pass-static |
| R15 | posedge flops on clk after buffer collapse; no async reset, latch, memory, init, loop or black box | `lint_*` (Yosys `check -assert`, `scc`, forbidden types, `check_interface.py`); `.sby` guards in every `fv_*`; `gate/evidence/clkbuf_00/` | static | pass-static |
| R16 | lint clean (internal UNUSEDSIGNAL waived) | `lint_*` (`check_lint.py`; golden: `difference[12]`) | static | pass-with-waiver |
| R17 | 00: value specified only under A1–A4; everything else for all inputs | `fv_result_00` (`a_comp` conditioned by `spec_p` = reference valid && denominator unchanged; no assumptions); `fv_proto_00` (protocol for all inputs); cover `c_unspec` (out-of-domain completions are reached, so the condition is not vacuously true) | proof | proven |
| R18 | controller use (00 under A1–A4) | subset of R1–R11 at 00 | proof | proven |
| R19 | model = `divide_round` | `selftest` (30,732 points; same domain) | static | pass-static |
| — | formal reference = definition | `refcheck` (`ref_divider_seq.v` vs model on every edge point) | edge/spot | pass-static |
| — | checker sanity | `fv_sanity_pu_00`, `fv_sanity_lat_11`, `fv_sanity_round_00/11`, `fv_sanity_stab_00` (must fail; traces in `formal/runs/divider_sanity_*/engine_0/`) | negative control | failed-as-expected |
| — | proofs not vacuous | assertion counts checked per task (proto 6, result 16 / 18, cover 7 + 14 / 15, sanity 1 / 6 / 7); all covers reached; no assumptions | model inspection | — |
| — | candidate vs golden | `eqy_rtl_00`, `eqy_rtl_11` (RTL), `eqy_rtl` (gate) | EQY | proven |
| — | gate-level reuse | `gate/evidence/golden_00_gf180/`, `golden_11_gf180/`, `clkbuf_00/`: `results.json` all_ok | all methods | all_ok |

## Coverage gaps (stated limits)

- **The result proof is white-box.** `fv_result_*` needs the golden's register names. For a
  candidate without them it reports `unsupported` (non-gating). Its result correctness then rests
  on `eqy_rtl_*` (strict equivalence with the golden, which `fv_result_*` characterises) plus the
  sampled `edge_*`. Gate netlists do not run `fv_result_*`.
- **EQY is strict.** It does not use A1–A4, so a 00 candidate that exploits those don't-cares
  fails it. It also needs the golden's register names (or their alias names `divisor`/`invalid`).
  Re-encoded state needs a reviewed match or a domain-restricted proof.
- **A1–A4 are assumptions of this module contract.** They are discharged nowhere yet; the
  controller-level contract must prove them (SPEC §2 gives the argument).
- **Covers run on RTL only** (gate covers take minutes). Gate netlists still run the black-box
  proofs, the negative controls, EQY and the edge item.
- **X-freedom** is checked by Icarus at the edge/spot cycles only.
- **Flop models.** Gate-level formal uses the liberty flop model and simulation the UDP; both views
  must pass. Combinational cells use the PDK Verilog model everywhere (library trust).
- **Mutation testing** belongs to Agent 2. `evidence/smoke_mutants/` is Agent 1's smoke check only.
