# exp_lut Phase 1: independent review of Agent 1's verification contract (Agent 2)

Scope: `pd_flow/modules/exp_lut/verif/` at commit **`1437ea8`** (the D9/D9b amendment of `ec61c41`),
unmodified (`git status` of `verif/` clean; file hashes in
[`contract_hash_1437ea8.txt`](contract_hash_1437ea8.txt)). Requirements were derived first, before any
`verif/` file was read: [`EXPECTED.md`](EXPECTED.md). Golden: `snapshot/exp_lut.v` (SHA-256
`873546cc…`, equal to `baseline/original_rtl/`). Agent 2 used at most 2 jobs throughout and never read
`opt/`.

Verification rules applied: D9 (no exhaustive testing; formal acceptance) and D9b (combinational logic:
edge cases plus spot checks; sequential logic: SBY; EQY against the golden is mandatory for candidates;
a mutant may be killed by an edge/spot item or by a formal item). Work done before D9 (a partial
mutation campaign on `ec61c41`, and my own exhaustive Verilator sweeps) is kept in
[`superseded_pre_D9/`](superseded_pre_D9/README.txt) for traceability only. It is not evidence here.

## Verdict: **CHANGES REQUIRED** (one blocking finding, a one-line fix, already validated)

The contract is sound and close to complete. 52 of 53 must-kill mutants (RTL and GF180 gate level) are
killed by gating items: all 52 by a formal item (SBY or EQY), and 49 of them also by the edge/spot items. All 10
expected survivors are EQY-proven equivalent. The single surviving must-kill mutant, m34 (default
`REGISTERED` changed from 1 to 0), shows a **fail-open bug** in the default-parameter check
(**B1**). With the exact edit in §5 applied, m34 fails `lint_r1`, and the golden and an equivalent
mutant still pass 16/16 ([`formal_checks/fix_B1/`](formal_checks/fix_B1/)). After B1 is applied and the
golden evidence is regenerated, I have no remaining blocking objection: the verdict becomes APPROVE
without a further review round. Rerun `m34` and the golden to confirm.

## 1. Reproduction

| Run | Result |
|---|---|
| Clean copy (`git archive 1437ea8` of `verif/`, `snapshot/`, `python/src` into the scratchpad), golden RTL | 16/16 gating ok, smoke 3/3, `all_ok = true`, 19.3 s. Every item id and status identical to `verif/results.json` ([`rerun/clean_rtl/`](rerun/clean_rtl/results.json)) |
| Same copy, `--gate --registered 0`, golden r0 netlist | 7/7 gating ok, 9.3 s, identical to `gate/evidence/golden_r0_gf180` ([`rerun/clean_gate_r0/`](rerun/clean_gate_r0/results.json)) |
| Same copy, `--gate --registered 1`, golden r1 netlist | 13/13 gating ok, smoke 3/3, 35.2 s, identical to `gate/evidence/golden_r1_gf180` ([`rerun/clean_gate_r1/`](rerun/clean_gate_r1/results.json)) |
| My GF180 netlists (`gate_synth.sh`, same recipe) | byte-identical to `verif/gate/netlists/exp_lut_r{0,1}_gf180.v` (2,414.72 / 2,996.45 µm²) |

## 2. Coverage against EXPECTED.md

| EXPECTED | Contract | Assessment |
|---|---|---|
| E1 table (25 entries + first zero) | R1/R3; `edge_r*` hits every D' 0..34 at every shift (`half_way` points), every transition ±1; `fv_prove_r1` `a_load` for all D at r1; `eqy_rtl_r*` | covered. All 6 LUT-entry mutants (m01–m06), incl. the near-tie entries D' = 8 and 25, are killed by `edge_r0` **and** `edge_r1` |
| E2 rounding half up, s = 0 not rounded | R2; `half_way` class `(2k+1)·2^(s−1)` −1/0/+1; `fv_sanity_trunc_r1` | covered. Truncation, tie-down and ties-to-even (m07–m09) are killed by edge and formal |
| E3 shift selection, boundaries s = 0, 1, 7/8, 15 | every shift in every edge class | covered (m10 shift 8, m11 shift 0, m12 shift 15 killed by edge) |
| E4 saturation (a) D' 25..31, (b) carry to 32, (c) dropped high bits, (d) D ≥ 2^20 incl. D[21] | R3/R4; classes `dprime_edge` (D' 24/25), `half_way` up to k = 33, `d20_set`, `d21_set`, `d21_d20_set`, `fixed`; targeted R3/R4 checks | covered (m13, m14, m15, m16, m18, m20 killed by edge) |
| E5 all output bits, 255 | `c_w255` cover; edge points | covered (m06) |
| E6 r0 combinational, `done = start`, no clk/rst_n dependence | R6/R7; `edge_r0` toggles clk/rst_n/start at every point; `lint_r0` (no state); `eqy_rtl_r0` | covered (m30–m33) |
| E7 r1 reset priority, load, hold, latency 1, done pulse | R8–R12; SBY `a_rst/a_load/a_hold/a_step_*`, covers, `fv_sanity_lat0_r1` | covered, proven (m21–m28) |
| E8 power-up, no init | R13; free DUT state, `.sby` init guard, `fv_sanity_pu_r1`, `lint` | covered (m29 killed by lint and the init guard) |
| E9 independence | as E6/E7 | covered |
| Interface, **default `REGISTERED = 1`** | R14; the `lint_r1` default-parameter step | **not enforced: B1** (m34 survives) |
| U2: D[21] unreachable in context, but specified | SPEC §2 and R4, gap stated in RTM | agreed (see §3.4) |
| Independent reference | model plus two formal formulations | agreed (see §3.1) |

## 3. Audit findings

Severity: **B** = blocking, **NB** = non-blocking.

### 3.1 Independence of the references (no finding)
- Agent 1's model computes D' with `Fraction` and W with `math.exp` plus 60-digit `Decimal` (which must agree), and
  uses a monotone bound for D' ≥ 25. The formal harness uses wA (23-bit add-and-shift) and wB (a threshold count). The
  edge bench uses the model's file plus its own double-precision formula. None of them reads the RTL table or uses the RTL's
  guard bit or staged shifter.
- **My reference is a different formulation**:
  - table entries certified by a rigorous rational interval (Taylor series of e^(1/4) with a remainder bound),
    with no floating point;
  - D' never computed by shifting (threshold count `#{k : D ≥ ceil((k−½)·2^s)}`);
  - my own REGISTERED = 1 next-state expression.

  Formally checked against the golden ([`ref/run_ref.sh`](ref/run_ref.sh), outputs in `ref/out/`): EQY golden vs
  `ref_exp_lut.v` **PASS** at REGISTERED = 0 (combinational, complete) and at REGISTERED = 1 (state matched, depth-1
  induction). A Yosys SAT miter, golden vs `ref_threshold.v`, gives **SUCCESS**. Negative controls: m19 FAILs at r0 and r1,
  m23 FAILs at r1 only.
- **Shared include (coordinator question).** wA and wB share `ref_table.vh`. A common-mode error there
  would make both references wrong together. I compared it entry by entry with my independent table:
  `ref_wtab` 64/64 and `ref_thr` 400/400 identical, and all 352 interval-file endpoints agree
  ([`formal_checks/shared_include/compare.txt`](formal_checks/shared_include/compare.txt)). The
  sharing is therefore acceptable. The residual risk (a model bug that matches an RTL bug) is eliminated
  by an independent derivation.

### 3.2 Assumptions, vacuity, proof validity (no finding)
- No `assume`, `restrict`, `anyconst` or `anyseq` in `exp_lut_props.sv` or `exp_lut.sby` (grep). The DUT has no init. The
  init guard runs before `flatten` (max_reg N1 lesson applied correctly).
- Vacuity: the assertion count is checked per task (6), 10/10 covers are reached and the antecedents of
  `a_rst/a_load/a_hold/a_seq` are covered. All 3 negative controls are refuted.
- "Proven" claims: `fv_prove_r1` closes at **depth 1** with the unchanged harness
  ([`formal_checks/depth1/status.txt`](formal_checks/depth1/status.txt)), so the 1-inductiveness claim
  holds and depth 4 is ample. abc pdr agrees. `proven` is used only for SBY proofs and EQY PASS.
  The edge items are `pass-edge-spot` → label `pass-sampled`, and smoke is non-gating. The labels are honest.
- Single-clock premise: discharged by the `.sby` guards and lint (m27 async, m28 negedge, m33 latch, g05
  dffnq and g08 latq are all rejected).

### 3.3 `proc -norom` everywhere (coordinator question; no finding)
- It is **needed, not masking**. With plain `proc`, Yosys turns the golden's weight `case` into a
  `$mem_v2` ROM. The `.sby` `$mem*` guard then rejects the golden itself (`prove_r1` and `cover_r1` ERROR,
  [`formal_checks/rom/status.txt`](formal_checks/rom/status.txt)), and EQY's sat strategy refuses
  memory partitions (seen on `ec61c41`: `eqy_rtl` inconclusive). `-norom` only changes how a constant
  table is represented: the same logic, not a ROM cell. It changes no semantics and keeps the `$mem`
  guard strict for real memories.
- Consequence for Agent 3: an explicit memory array (e.g. `reg [7:0] t [0:24]`) is still rejected. See §6.

### 3.4 R4, W = 0 for D ≥ 2^20 including D[21] (coordinator question; no finding)
- The **D[20] part is a real, reachable requirement**. The consumed range is D ≤ 2,088,960 = 0x1FE000,
  which includes D ≥ 2^20. For every shift ≤ 15 these D give D' ≥ 32, so W = 0 is just `f` (not an extra rule).
  Mutant m15 (no 2^20 check: D = 2^20 gives 255) is an in-context bug and is killed.
- The **D[21] part** (D ≥ 2^21) is unreachable with a consistent tape. It is reachable with an inconsistent tape,
  or with `cont = 1` before any fresh run (documented garbage), where a negative M − S wraps to D ≥ 2^21. W = 0 is the safe
  output there (no spurious weight). It is also the golden's behaviour and PHASE0 invariant 3. Specifying it
  costs nothing measurable: the mapped netlist that ignores D[21] (s_m14) is **larger** (2,603.5 vs
  2,414.7 µm²). **Keep R4 as specified.** Exploiting the don't-care is a cluster-level (D7) question
  and needs the reviewed amendment the SPEC already describes.

### 3.5 Lint waiver on unused clk/rst_n at gate r0 (coordinator question; no finding)
- The waiver is justified and narrow. An r0 netlist must have no state (`check_interface.py`), so `clk` and
  `rst_n` are necessarily unconnected. The regex is anchored to exactly `Signal is not used: 'clk'|'rst_n'`,
  gate mode with `--registered 0` only.
- Evidence it does not swallow other warnings:
  - g09 (an internal LUT input tied) fails `lint_r0` on `UNUSEDSIGNAL '_027_'`;
  - s_m14 fails it on `'D'[21]`;
  - both of them still show `port_waived=2`.

### 3.6 **B1 (blocking): the default-parameter check cannot fail**
`verif/run_all.sh` line 85:
```
"$PY" "$VERIF/lint/check_interface.py" lint_default.json --registered 1 | sed 's/^RESULT interface/RESULT default_param/' || r4=1
```
The status of a pipeline is the status of `sed`, so `r4` stays 0 even when the check fails. On m34
(`parameter REGISTERED = 0`) the log shows `RESULT default_param ... flop_bits=0 errors=1` followed by
`default_rc=0`, and `lint_r1` passes. R14 ("default 1, the block test instantiates the default")
is therefore not enforced by any gating item. `test/blocks` would catch it, but the contract
does not. The same line is in `ec61c41`. The other pipes in `run_all.sh` are fine: the console `tee` uses `PIPESTATUS`.
Exact fix in §5.

### 3.7 Gate mode, `eqy_rtl`, clock-buffer flatten (no finding)
- `eqy_rtl` (both sides `proc -norom`) proves the golden r0 netlist (combinational, complete) and the r1 netlist
  (9 state bits matched by name).
- g06 (all 9 flops behind one `clkbuf_1`, as post-CTS) passes all 13 gating items. The `.sby` flattens
  before `prep` and lint collapses the buffer, so R15 holds after buffer collapse, consistently in both checks.
- EQY cannot see clock polarity (g05 dffnq and m28 are EQY-PASS in my classification), but lint and the `.sby` guards
  reject both, as SPEC §6 says.
- The two flop views (UDP in simulation, liberty in Yosys) both run on every r1 netlist.

### 3.8 Edge/spot set blind spots (coordinator question; NB2, informational)
- Every **realistic** single-entry or boundary mutant is killed by `edge_*` itself, not only by EQY:
  - LUT entries m01–m06;
  - an entry wrong at a single shift (m36, r0 only, 2,048 inputs);
  - shift-0 out-of-range (m11, 25 inputs);
  - the rounding carry (m13);
  - D[21] (m14) and the 2^20 check (m15);
  - stage checks (m18).

  The rare single points m19/m35 (D = 1337, shift 7) and m38/m39 (an X at that point) are also killed by
  `edge_*`. The spot checks sample the small non-zero region at low shifts densely (shift 7 has 3,392 non-zero D).
- The edge set's blind spot is **interior sub-ranges at large shifts**: m37 (W − 1 for D in
  3000..3010 at shift 10, inside the D' = 3 interval, away from every boundary) passes `edge_r0`. It is killed only by
  `eqy_rtl_r0`. This is inherent to D9b and accepted. EQY is the only full-domain check of the r0 function,
  which RTM "Coverage gaps" already states. No change required. Keep `eqy_rtl_r0` gating for every candidate.
- Other mutants killed only by non-edge items: m29 (init value; lint and the `.sby` init guard) and g08 (latch on
  `done`; lint, SBY and EQY). Both are structural.

### 3.9 X checking (NB1)
D9 asks for formal X-propagation. The contract's X check is Icarus 4-state at the 105,418 edge points
(SPEC §7), which is directed rather than formal. EQY did flag every X mutant I tried
(m17, m38, m39 fail `eqy_rtl_r*`), and a gate netlist cannot carry an X constant, so the practical risk is low. A formal check
is cheap and complete. I validated one ([`formal_checks/xprop/run_xprop.sh`](formal_checks/xprop/run_xprop.sh)):
Yosys `sat -enable_undef -set-def-inputs` (r1: defined initial state, one step, which is inductive because W and `done` are the
state). It gives "no model found" on the golden and e02 at r0 and r1, and "model found" on m17 (r0, r1), m38 (r0 only) and
m39 (r0, r1) ([`results.txt`](formal_checks/xprop/results.txt)). Proposed edit in §5.

### 3.10 Cosmetic (NB3) and smoke (NB4)
- NB3: `model/golden_model.py` docstring "255 * e^(-25/4) = 0.4928..." and SPEC §1 "0.493" should read
  **0.4923** (certified: 0.492266; tie margin 0.0077 is correctly stated elsewhere).
- NB4: in the non-gating `sim/tb_vectors.sv`, D and shift are assigned by `$sscanf` before `w_before` is sampled,
  so its comb-path check does not cover D/shift changes. The gating `tb_edge.sv` samples first, so it is correct. Optional fix: read
  into temporaries and assign D/shift after `w_before = W`.

## 4. Mutation testing (contract `1437ea8`, unmodified, gating items only)

Driver: [`run_mutants.py`](run_mutants.py) (one mutant at a time, `--jobs 2`; gate mutants get
`--registered` from the manifest). Generators: [`make_mutants.py`](make_mutants.py) (44 RTL, one checked
edit each, all lint-clean except the intended structural ones) and
[`make_gate_mutants.py`](make_gate_mutants.py). The gate mutants are 9 hand edits of the golden GF180 netlists
(`g*`) plus 10 mapped netlists of RTL mutants (`s_*`, [`gate_synth.sh`](gate_synth.sh)). Raw results:
[`mutation_results.json`](mutation_results.json) and `mutation_runs/<name>/`. Formal (EQY) classification
of every mutant against the golden: [`equiv/classification.json`](equiv/classification.json) and
`equiv/classify/` ([`equiv/run_eqy.sh`](equiv/run_eqy.sh), [`equiv/classify_all.sh`](equiv/classify_all.sh)).

### Score

| Category | Runs | Killed | Survived | Notes |
|---|---:|---:|---:|---|
| Functional bugs (RTL 30, gate 10) | 40 | **40** | 0 | 40/40 killed by a formal item (SBY or EQY); 39/40 also by `edge_*` (m37 is EQY-only, §3.8) |
| Out-of-context bugs: wrong at block level, invisible in the chip (m14, m20, m30, m31, s_m14, s_m30) | 6 | **6** | 0 | all killed by `edge_*` and by EQY |
| Structural / interface: async reset, negedge, init, r0 latch, default param (RTL m27, m28, m29, m33, m34); dffnq, latq (gate g05, g08) | 7 | 6 | **1** | **m34 survives: B1**. m29 and g08 are killed by lint and formal, not by edge |
| **Must-kill total** | **53** | **52** | **1** | 98.1 % (100 % after B1); 52/53 killed by a formal item, 49/53 by `edge_*` |
| Equivalent rewrites (RTL e01–e05; gate g03, g04, g06, s_e02, s_e04) | 10 | 0 | 10 | all **EQY-proven equivalent** at their configuration(s) |
| **All runs** | **63** | 52 | 11 | 44 RTL + 19 gate |

(Exact per-class counts are in `mutation_results.json` `summary`. The class of each run is in the table below.)

Notable results:
- g03 (input A2 of cell `_139_` tied to 1) turned out to be **equivalent**: EQY PASS. ABC left a logically
  redundant input in the golden r0 mapping. That is a small mapping slack and not a contract issue.
- The EQY classification agrees with the contract on every run. The only EQY-PASS must-kill mutants are m28, m29,
  m34 and g05. Their faults are, respectively, clock polarity, init, parameter default and polarity, which are outside EQY's view by nature.
  The contract kills m28, m29 and g05 by lint and the `.sby` guards. m34 is B1.

### Survivors
| Survivor | Verdict |
|---|---|
| e01_swap_19_20, e02_fullwidth_round, e03_ge_2_20, e04_r1_mux_hold, e05_explicit_zeros | EQY PASS at REGISTERED 0 and 1 (`equiv/classify/<name>_R{0,1}`) |
| gate g03_tie_input, g04_buf_internal, s_e02_fullwidth_round (r0); g06_clkbuf, s_e04_r1_mux_hold (r1) | EQY PASS against the golden (`equiv/classify/gate_<name>_R*`) |
| **m34_default_param0** | **contract gap, B1** (EQY PASS is expected: both configurations are identical, only the default differs) |

EQY discriminates: the golden self-checks PASS, while m01–m27, m30–m33, m35–m39 and every functional gate mutant
FAIL in the configuration(s) they affect.

### Per-mutant results

Key: edge = `edge_r0`/`edge_r1` (shown as `edge0`/`edge1` or `r0`/`r1`); formal = SBY items (`prove1`, `pdr1`,
`cover1`, `sanity_*1`) and EQY (`eqy_rtl0/1`, `eqy_rtl`); static = lint/build. The last column is my
own formal EQY of the mutant against the golden.

| # | Mutant | Class | Description | Outcome (gating ok) | edge | formal / EQY | static | EQY vs golden |
|---|---|---|---|---|---|---|---|---|
| 1 | `e01_swap_19_20` | equivalent | entries D'=19 and D'=20 swapped (both 2) | survived (16/16) | none | none | none | R0:PASS R1:PASS |
| 2 | `e02_fullwidth_round` | equivalent | full-width reformulation: D' = (D + 2^(s-1)) >> s at 23 bits, W = D' < 25 ? table : 0 | survived (16/16) | none | none | none | R0:PASS R1:PASS |
| 3 | `e03_ge_2_20` | equivalent | OR-reduce of D[21:20] written as D >= 2^20 | survived (16/16) | none | none | none | R0:PASS R1:PASS |
| 4 | `e04_r1_mux_hold` | equivalent | REGISTERED=1: if (start) W_r <= weight written as W_r <= start ? weight : W_r | survived (16/16) | none | none | none | R0:PASS R1:PASS |
| 5 | `e05_explicit_zeros` | equivalent | explicit zero entries D'=25..31 added before the default | survived (16/16) | none | none | none | R0:PASS R1:PASS |
| 6 | `m01_lut8_34` | functional-bug | entry D'=8 35 -> 34 (near-tie 34.5105 truncated/rounded down) | killed (10/16) | edge0, edge1 | pdr1, prove1, eqy_rtl0, eqy_rtl1 | none | R0:FAIL R1:FAIL |
| 7 | `m02_lut25_1` | functional-bug | D'=25 gives 1 instead of 0 (near-tie 0.4923 rounded up) | killed (10/16) | edge0, edge1 | pdr1, prove1, eqy_rtl0, eqy_rtl1 | none | R0:FAIL R1:FAIL |
| 8 | `m03_lut1_198` | functional-bug | entry D'=1 off by one: 199 -> 198 | killed (10/16) | edge0, edge1 | pdr1, prove1, eqy_rtl0, eqy_rtl1 | none | R0:FAIL R1:FAIL |
| 9 | `m04_lut20_1` | functional-bug | entry D'=20 off by one: 2 -> 1 (equal-neighbour region) | killed (10/16) | edge0, edge1 | pdr1, prove1, eqy_rtl0, eqy_rtl1 | none | R0:FAIL R1:FAIL |
| 10 | `m05_lut24_0` | functional-bug | last nonzero entry D'=24: 1 -> 0 | killed (10/16) | edge0, edge1 | pdr1, prove1, eqy_rtl0, eqy_rtl1 | none | R0:FAIL R1:FAIL |
| 11 | `m06_lut0_254` | functional-bug | entry D'=0: 255 -> 254 (W[0] bit stuck 0 at the peak) | killed (9/16) | edge0, edge1 | cover1, pdr1, prove1, eqy_rtl0, eqy_rtl1 | none | R0:FAIL R1:FAIL |
| 12 | `m07_truncate` | functional-bug | no rounding: D' = D >> s (rounding bit ignored) | killed (9/16) | edge0, edge1 | pdr1, prove1, sanity_trunc1, eqy_rtl0, eqy_rtl1 | none | R0:FAIL R1:FAIL |
| 13 | `m08_tie_down` | functional-bug | ties round down: D' = (D + 2^(s-1) - 1) >> s (round-half-down, full-width reformulation) | killed (10/16) | edge0, edge1 | pdr1, prove1, eqy_rtl0, eqy_rtl1 | none | R0:FAIL R1:FAIL |
| 14 | `m09_tie_even` | functional-bug | ties round to even (banker's rounding of D/2^s; full-width reformulation) | killed (10/16) | edge0, edge1 | pdr1, prove1, eqy_rtl0, eqy_rtl1 | none | R0:FAIL R1:FAIL |
| 15 | `m10_shift8_decode` | functional-bug | shift = 8 decoded as shift = 0 (stage-8 select boundary off by one) | killed (10/16) | edge0, edge1 | pdr1, prove1, eqy_rtl0, eqy_rtl1 | none | R0:FAIL R1:FAIL |
| 16 | `m11_shift0_oor` | functional-bug | shift = 0: D = 32..63 not flagged out of range (last stage check skipped at s=0) | killed (10/16) | edge0, edge1 | pdr1, prove1, eqy_rtl0, eqy_rtl1 | none | R0:FAIL R1:FAIL |
| 17 | `m12_s15_noround` | functional-bug | shift = 15 only: rounding bit ignored | killed (10/16) | edge0, edge1 | pdr1, prove1, eqy_rtl0, eqy_rtl1 | none | R0:FAIL R1:FAIL |
| 18 | `m13_carry_lost` | functional-bug | rounding carry to D'=32 not flagged (index[5] dropped): e.g. s=1, D=63 gives 255 | killed (10/16) | edge0, edge1 | pdr1, prove1, eqy_rtl0, eqy_rtl1 | none | R0:FAIL R1:FAIL |
| 19 | `m14_bit21_ignored` | out-of-context-bug | D[21] ignored (D >= 2^21 aliases to D - 2^21); unreachable with a consistent tape | killed (10/16) | edge0, edge1 | pdr1, prove1, eqy_rtl0, eqy_rtl1 | none | R0:FAIL R1:FAIL |
| 20 | `m15_bit20_ignored` | functional-bug | D >= 2^20 check removed: D = 2^20 gives 255 | killed (10/16) | edge0, edge1 | pdr1, prove1, eqy_rtl0, eqy_rtl1 | none | R0:FAIL R1:FAIL |
| 21 | `m16_default_1` | functional-bug | table default D'=25..31 gives 1 (saturation region nonzero) | killed (10/16) | edge0, edge1 | pdr1, prove1, eqy_rtl0, eqy_rtl1 | none | R0:FAIL R1:FAIL |
| 22 | `m17_default_x` | functional-bug | table default D'=25..31 gives X (unspecified; 2-state sims may read 0) | killed (10/16) | edge0, edge1 | pdr1, prove1, eqy_rtl0, eqy_rtl1 | none | R0:FAIL R1:FAIL |
| 23 | `m18_stage_check` | functional-bug | stage-4 discarded-bit check dropped: shift without bit 2 and D bits lost from stage8[12:9] | killed (10/16) | edge0, edge1 | pdr1, prove1, eqy_rtl0, eqy_rtl1 | none | R0:FAIL R1:FAIL |
| 24 | `m19_rare_point` | functional-bug | one rare point: D = 1337, shift = 7 (D'=10) gives 22 instead of 21 (1 of 2^26 inputs) | killed (10/16) | edge0, edge1 | pdr1, prove1, eqy_rtl0, eqy_rtl1 | none | R0:FAIL R1:FAIL |
| 25 | `m20_rare_highD` | out-of-context-bug | one rare point above the consistent-tape range: D = 22'h3FFFFF, shift = 15 gives 255 | killed (10/16) | edge0, edge1 | pdr1, prove1, eqy_rtl0, eqy_rtl1 | none | R0:FAIL R1:FAIL |
| 26 | `m21_r1_latency2` | functional-bug | REGISTERED=1: two-cycle latency (extra W and done stage) | killed (11/16) | edge1 | pdr1, prove1, eqy_rtl1 | lint1 | R0:PASS R1:FAIL |
| 27 | `m22_r1_comb_bypass` | functional-bug | REGISTERED=1: W shows the new weight combinationally in the start cycle (latency 0) | killed (11/16) | edge1 | pdr1, prove1, sanity_lat01, eqy_rtl1 | none | R0:PASS R1:FAIL |
| 28 | `m23_r1_load_always` | functional-bug | REGISTERED=1: W reloads every cycle (no hold while start = 0) | killed (11/16) | edge1 | cover1, pdr1, prove1, eqy_rtl1 | none | R0:PASS R1:FAIL |
| 29 | `m24_r1_W_noreset` | functional-bug | REGISTERED=1: W not cleared by reset (done still is) | killed (11/16) | edge1 | cover1, pdr1, prove1, eqy_rtl1 | none | R0:PASS R1:FAIL |
| 30 | `m25_r1_start_over_reset` | functional-bug | REGISTERED=1: start has priority over reset for W | killed (12/16) | edge1 | pdr1, prove1, eqy_rtl1 | none | R0:PASS R1:FAIL |
| 31 | `m26_r1_done_stretch` | functional-bug | REGISTERED=1: done stays high one extra cycle | killed (11/16) | edge1 | pdr1, prove1, eqy_rtl1 | lint1 | R0:PASS R1:FAIL |
| 32 | `m27_r1_async_reset` | structural | REGISTERED=1: asynchronous reset (clears W/done when rst_n falls, before the edge) | killed (7/16) | edge1 | cover1, pdr1, prove1, sanity_lat01, sanity_pu1, sanity_trunc1, eqy_rtl1 | lint1 | R0:PASS R1:FAIL |
| 33 | `m28_r1_negedge` | structural | REGISTERED=1: negedge flops | killed (8/16) | edge1 | cover1, pdr1, prove1, sanity_lat01, sanity_pu1, sanity_trunc1 | lint1 | R0:PASS R1:PASS |
| 34 | `m29_r1_initval` | structural | REGISTERED=1: initial values on W_r/done_r (no ASIC power-up value) | killed (9/16) | none | cover1, pdr1, prove1, sanity_lat01, sanity_pu1, sanity_trunc1 | lint1 | R0:PASS R1:PASS |
| 35 | `m30_r0_rst_gates_W` | out-of-context-bug | REGISTERED=0: W forced to 0 while rst_n = 0 (never observed in the chip) | killed (14/16) | edge0 | eqy_rtl0 | none | R0:FAIL R1:PASS |
| 36 | `m31_r0_done_zero` | out-of-context-bug | REGISTERED=0: done tied 0 (chip ties start = 0) | killed (14/16) | edge0 | eqy_rtl0 | none | R0:FAIL R1:PASS |
| 37 | `m32_r0_registered_W` | functional-bug | REGISTERED=0: W registered (one-cycle latency in the chip configuration) | killed (13/16) | edge0 | eqy_rtl0 | lint0 | R0:FAIL R1:PASS |
| 38 | `m33_r0_latch` | structural | REGISTERED=0: W through a transparent-high latch on clk | killed (12/16) | edge0 | eqy_rtl0 | lint0, build0 | R0:FAIL R1:PASS |
| 39 | `m34_default_param0` | structural | interface: default REGISTERED changed 1 -> 0 (test/blocks instantiates the default) | survived (16/16) | none | none | none | R0:PASS R1:PASS |
| 40 | `m35_r0_rare_point` | functional-bug | REGISTERED=0 only: one interior point D = 1337, shift = 7 (D'=10) gives 22 instead of 21; R1 correct | killed (14/16) | edge0 | eqy_rtl0 | none | R0:FAIL R1:PASS |
| 41 | `m36_r0_entry_one_shift` | functional-bug | REGISTERED=0 only: entry D'=6 wrong (57 -> 56) at shift 11 only (2,048 D values) | killed (14/16) | edge0 | eqy_rtl0 | none | R0:FAIL R1:PASS |
| 42 | `m37_r0_mid_interval` | functional-bug | REGISTERED=0 only: W off by one for D in [3000, 3010] at shift 10 (inside the D'=3 interval, away from every boundary) | killed (15/16) | none | eqy_rtl0 | none | R0:FAIL R1:PASS |
| 43 | `gate_g01_nand2_to_nor2_W3` | functional-bug | R0: cell _097_ (drives W[3]) nand2_1 replaced by nor2_1 | killed (5/7) | edge0 | eqy_rtl | none | R0:FAIL |
| 44 | `gate_g02_swap_W0_W1` | functional-bug | R0: output nets W[0] and W[1] swapped | killed (5/7) | edge0 | eqy_rtl | none | R0:FAIL |
| 45 | `gate_g03_tie_input` | equivalent | R0: input A2 of cell _139_ tied to 1'b1 (found redundant: exhaustive sweep 0 mismatches; EQY to confirm) | survived (7/7) | none | none | none | R0:PASS |
| 46 | `gate_g04_buf_internal` | equivalent | R0: a buf_1 inserted on the W[3] output (equivalent; models resizer buffering) | survived (7/7) | none | none | none | R0:PASS |
| 47 | `gate_g05_dffnq_W0` | structural | R1: flop W[0] replaced by negative-edge dffnq_1 | killed (5/13) | edge1 | cover1, pdr1, prove1, sanity_lat01, sanity_pu1, sanity_trunc1 | lint1 | R1:PASS |
| 48 | `gate_g06_clkbuf` | equivalent | R1: all 9 flops clocked through one clkbuf_1 from clk (equivalent; models a post-CTS netlist) | survived (13/13) | none | none | none | R1:PASS |
| 49 | `gate_g07_dswap_W6_W7` | functional-bug | R1: D inputs of flops W[6] and W[7] swapped | killed (9/13) | edge1 | pdr1, prove1, eqy_rtl | none | R1:FAIL |
| 50 | `gate_g08_latq_done` | structural | R1: done flop replaced by latch latq_1 (E = clk, transparent high) | killed (8/13) | none | cover1, pdr1, prove1, eqy_rtl | lint1 | R1:FAIL |
| 51 | `gate_g09_stuck_W3_in` | functional-bug | R0: input A1 of cell _097_ (drives W[3]) tied to 1'b1 (stuck-at-1) | killed (4/7) | edge0 | eqy_rtl | lint0 | R0:FAIL |
| 52 | `gate_s_e02_fullwidth_round` | equivalent | mapped GF180 netlist (REGISTERED=0) of RTL mutant e02_fullwidth_round (full-width reformulation: D' = (D + 2^(s-1)) >> s at 23 bits, W = D' < 25 ? table : 0) | survived (7/7) | none | none | none | R0:PASS |
| 53 | `gate_s_e04_r1_mux_hold` | equivalent | mapped GF180 netlist (REGISTERED=1) of RTL mutant e04_r1_mux_hold (REGISTERED=1: if (start) W_r <= weight written as W_r <= start ? weight : W_r) | survived (13/13) | none | none | none | R1:PASS |
| 54 | `gate_s_m01_lut8_34` | functional-bug | mapped GF180 netlist (REGISTERED=0) of RTL mutant m01_lut8_34 (entry D'=8 35 -> 34 (near-tie 34.5105 truncated/rounded down)) | killed (5/7) | edge0 | eqy_rtl | none | R0:FAIL |
| 55 | `gate_s_m13_carry_lost` | functional-bug | mapped GF180 netlist (REGISTERED=0) of RTL mutant m13_carry_lost (rounding carry to D'=32 not flagged (index[5] dropped): e.g. s=1, D=63 gives 255) | killed (5/7) | edge0 | eqy_rtl | none | R0:FAIL |
| 56 | `gate_s_m14_bit21_ignored` | out-of-context-bug | mapped GF180 netlist (REGISTERED=0) of RTL mutant m14_bit21_ignored (D[21] ignored (D >= 2^21 aliases to D - 2^21); unreachable with a consistent tape) | killed (4/7) | edge0 | eqy_rtl | lint0 | R0:FAIL |
| 57 | `gate_s_m19_rare_point` | functional-bug | mapped GF180 netlist (REGISTERED=0) of RTL mutant m19_rare_point (one rare point: D = 1337, shift = 7 (D'=10) gives 22 instead of 21 (1 of 2^26 inputs)) | killed (5/7) | edge0 | eqy_rtl | none | R0:FAIL |
| 58 | `gate_s_m21_r1_latency2` | functional-bug | mapped GF180 netlist (REGISTERED=1) of RTL mutant m21_r1_latency2 (REGISTERED=1: two-cycle latency (extra W and done stage)) | killed (8/13) | edge1 | pdr1, prove1, eqy_rtl | lint1 | R1:FAIL |
| 59 | `gate_s_m23_r1_load_always` | functional-bug | mapped GF180 netlist (REGISTERED=1) of RTL mutant m23_r1_load_always (REGISTERED=1: W reloads every cycle (no hold while start = 0)) | killed (8/13) | edge1 | cover1, pdr1, prove1, eqy_rtl | none | R1:FAIL |
| 60 | `gate_s_m25_r1_start_over_reset` | functional-bug | mapped GF180 netlist (REGISTERED=1) of RTL mutant m25_r1_start_over_reset (REGISTERED=1: start has priority over reset for W) | killed (9/13) | edge1 | pdr1, prove1, eqy_rtl | none | R1:FAIL |
| 61 | `gate_s_m30_r0_rst_gates_W` | out-of-context-bug | mapped GF180 netlist (REGISTERED=0) of RTL mutant m30_r0_rst_gates_W (REGISTERED=0: W forced to 0 while rst_n = 0 (never observed in the chip)) | killed (5/7) | edge0 | eqy_rtl | none | R0:FAIL |
| 62 | `m38_r0_rare_x` | functional-bug | REGISTERED=0 only: W = X at one interior point (D = 1337, shift = 7); probes the X check off the edge set | killed (14/16) | edge0 | eqy_rtl0 | none | R0:FAIL R1:PASS |
| 63 | `m39_rare_x_both` | functional-bug | weight = X at one interior point (D = 1337, shift = 7), both configurations | killed (10/16) | edge0, edge1 | pdr1, prove1, eqy_rtl0, eqy_rtl1 | none | R0:FAIL R1:FAIL |

## 5. Exact changes

**B1 (blocking): make the default-parameter check able to fail.** `verif/run_all.sh` line 85, replace
```
                "$PY" "$VERIF/lint/check_interface.py" lint_default.json --registered 1 | sed 's/^RESULT interface/RESULT default_param/' || r4=1
```
with
```
                "$PY" "$VERIF/lint/check_interface.py" lint_default.json --registered 1 > lint_default.txt || r4=1
                sed 's/^RESULT interface/RESULT default_param/' lint_default.txt
```
Validated on a copy of `1437ea8`: golden 16/16, e01 16/16, m34 15/16 (`lint_r1` failed)
([`formal_checks/fix_B1/`](formal_checks/fix_B1/)). Then regenerate the golden evidence (`results.json`,
both gate evidence directories), add m34 (`review/mutants/m34_default_param0.v`) to
`evidence/smoke_mutants` as a must-fail case, and update `CONTRACT.sha256` and the gate file.

**NB1 (recommended; D9 X-propagation): add a formal X item.** In `run_all.sh` `job()`, add a case:
```
    xprop)  # r: formal X-propagation (D9): can W or done be X for defined inputs (r1: defined state)?
        local r=$1 chp="" res=ok sig S
        [ -z "$GATE" ] && chp="chparam -set REGISTERED $r exp_lut;"
        for sig in W done; do
            if [ "$r" = 0 ]; then S="-set-any-undef $sig"; else S="-seq 2 -set-init-def -set-any-undef-at 2 $sig"; fi
            yosys -q -l xprop_r${r}_$sig.log -p "read_verilog -sv exp_lut_fv.v; $chp hierarchy -top exp_lut; proc -norom; flatten; opt_clean; sat -enable_undef -set-def-inputs $S exp_lut" > /dev/null 2>&1
            grep -q 'SAT solving finished - no model found' xprop_r${r}_$sig.log || res="X reachable on $sig"
        done
        cat xprop_r${r}_*.log > "$log"
        det="formal X-propagation (yosys sat -enable_undef, defined inputs$([ "$r" = 1 ] && echo ', defined state, one inductive step')): $res"
        if [ "$res" = ok ]; then st=proven; ok=true; else st=failed; ok=false; fi ;;
```
and in the formal phase, before the `eqy_rtl` line (around line 317):
```
    for r in $CONFIGS; do echo "xprop_r$r xprop $r"; done
```
Document it in SPEC §7 and in RTM R5 (replacing "Icarus is the X check"). It was tested on RTL (`formal_checks/xprop/`). Check the gate
Yosys view once when adopting.

**NB3:** correct "0.4928..." / "0.493" to "0.4923" (model docstring, SPEC §1).
**NB4 (optional):** `sim/tb_vectors.sv`: sample `w_before`/`d_before` before assigning D and shift.

## 6. Constraints for Agent 3

These are behavioural and structural constraints that any optimized exp_lut (RTL or netlist) must respect.
They follow from the contract and from this review.
1. Keep the `REGISTERED` parameter and its **default value 1** (the block test instantiates the default). The
   chip uses 0. Both configurations must stay correct. Once B1 is applied, the contract checks the default.
2. The function is specified over the **full 22-bit unsigned D** and all 16 shifts, **including D[21] = 1 → W = 0**.
   Do not exploit the in-context don't-care (D < 2^21, or W unused outside VALUE) at block level. That
   needs a reviewed cluster-level (D7) amendment. It also has no measured value: ignoring D[21] mapped
   **+189 µm²** larger.
3. REGISTERED = 0: purely combinational. No state, latch or memory, and W independent of `clk`, `rst_n` and `start`
   (`done = start`).
4. Write tables as logic (`case`, `assign`, comparator chains). An explicit memory array becomes a `$mem`
   cell and is rejected by the `.sby` guard and by lint (`proc -norom` only covers `case` tables).
5. REGISTERED = 1: exactly 9 positive-edge flops on `clk`, with a synchronous active-low reset that wins over `start`, no
   async reset, no init values, no clock gating. To pass `eqy_rtl_r1` with the stock match, keep the state as
   `g_registered.W_r` / `g_registered.done_r` (driving W and `done` directly). A state re-encoding needs its own
   reviewed EQY match.
6. Every candidate needs `eqy_rtl_r0` / `eqy_rtl_r1` (RTL) or `eqy_rtl` (netlist) PASS against the golden.
   It is the only full-domain check of the r0 function (m37 shows the edge set alone is not sufficient).
7. Rounding is **half up** at every shift ≥ 1. The near-tie entries D' = 8 (35) and D' = 25 (0) are exact and
   must not come from a float-derived table.
8. Area hints (module level, not acceptance):
   - the golden r0 mapping contains a redundant cell input (g03: `_139_` A2 ties to 1 with no functional change);
   - the full-width rewrite e02 maps 2.2× larger (5,290 µm²).

## 7. Files

- `EXPECTED.md`: requirements derived before reading the contract (with my reference results updated for D9)
- `REVIEW.md` (this file), `mutation_results.json` (every run, killers by category, EQY verdicts, summary)
- `ref/`: independent reference (`ref_exact.py`, `table.json`, `ref_threshold.v`, `ref_exp_lut.v`, `run_ref.sh`
  formal-only, outputs in `ref/out/`); `exhaustive_sweep.cpp` and `run_ref_gate.sh` are pre-D9 and no longer used
- `mutants/` (44 RTL, `MANIFEST.json`), `gate_mutants/` (19 netlists and stat files, `MANIFEST.json`), `gate_netlists/`
- `mutation_runs/<name>/`: frozen-contract output per mutant
- `equiv/`: EQY scripts, per-mutant classification, survivor proofs, negative controls
- `formal_checks/`: depth-1 induction, plain `proc` (ROM) check, shared-include comparison, X-propagation
  prototype, B1 fix validation
- `rerun/`: clean-copy reruns of the golden (RTL, gate r0, gate r1)
- `golden_copy/`: hash-checked golden; `contract_hash_*.txt`: contract hashes audited
- `superseded_pre_D9/`: pre-D9 artifacts (not evidence)
