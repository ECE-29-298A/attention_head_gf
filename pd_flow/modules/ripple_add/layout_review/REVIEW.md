# ripple_add Phase 3: independent review of the layout plan (Agent 5)

Date: 2026-11-26. Reviewed: `layout_plan/` (PLAN.md, tables.md, gen_placement.py, validate_placement.py,
out/, chip_runs/) and the run trees `/Users/samuelzhang/ttharden/ra_<tag>`. I wrote my PDK and chip facts
(`INDEPENDENT_NOTES.md`) before reading the plan. No Agent 4 file, `src/`, PDK or reference file was edited.
Nothing was committed. No harden was run.

## Verdict: CHANGES REQUIRED (one blocking item, small and exact). The recommendation itself is APPROVED.

- **Keep the golden RTL in the shipped chip: APPROVED.** The raw metrics support it on every axis (§3).
- **Netlist and placement handoff: one blocking defect (B1).** The delivered MSB `xor3_1` puts the carry,
  which is the latest and most glitch-prone input, on the slowest input pin. That costs 1.95 ns on the
  module's critical path at ss. The plan then reports the resulting 2.4 ns difference as "harden noise". The
  fix is a generator constraint plus text corrections. **No new harden is needed**, because run `hyb` already
  measures the carry-on-A3 netlist.
- Everything else (connectivity, coordinates, PDK legality, taps, power, the integration mechanism) passed
  my own checks. The non-blocking items are clarity, over-build and Phase 4 risk notes.

## 1. What I checked independently, and the results

| Area | Method (mine, not Agent 4's scripts) | Result |
|---|---|---|
| Contract integrity | `shasum -c CONTRACT.sha256` | 17/17 OK |
| Connectivity N=22 | `verif/run_all.sh --rtl layout_plan/out/ripple_add_n22.v --gate 22 --out layout_review/contract_n22` | **10/10 ok**: proven (k-induction, abc pdr), covered 16/16, vectors and 5·10⁷ random pass-sampled, sanity failed as expected, lint pass |
| Connectivity N=12 | same with `--gate 12 --out layout_review/contract_n12` | **11/11 ok**, including pass-exhaustive 2²⁵ |
| Netlist content | `check_coords.py` netlist parse | 21 addf_1 + 1 xor3_1 (N=22), 11 + 1 (N=12), as claimed |
| Coordinates (chip anchors) | `check_coords.py`: own LEF tokenizer (`leftab.py`), rows/taps/endcaps/stripes parsed from the **baseline** final DEF | on-site (x = 3.36 + 0.56k), on-row, orientation legal for row parity (N/FN on N rows, FS/S on FS rows), LEF widths, no overlap with each other, taps or endcaps; N=12 and N=22 columns disjoint; bit i in relative row i in one column. PASS |
| Coordinates (standalone block cfgs) | same, against the block core in `block_n22_librelane.json` | PASS (37-site rows, 2-site endcaps both sides) |
| Legal anchor enumeration | own brute force over 39 × 607 against baseline taps and endcaps | N=22: 272 legal, 128 stripe-free; N=12: 442 / 208. Matches Agent 4 exactly |
| PDN at default anchors | M4 stripe x from the baseline DEF | no stripe, and therefore no rail via stack, over any column cell. PASS |
| Tap / latch-up rule | per-well nearest tap (same row, or the neighbour row that shares that well), with a 3.92 µm vertical term | worst **10.3 µm ≤ 15 µm** (DF.13_MV / DF.14_MV). The same-row tap alone is up to 19.3 µm (see N1) |
| Cells held in the chip (FIRM run `ra_final_fixed`) | final DEF and all 15 step DEFs from step 17 on | **34/34 at the exact location and orientation, FIXED, same master, at every step from ManualMacroPlacement to the final DEF**. 348 taps and 78 endcaps at positions identical to the baseline; PDN stripes identical; 39 rows (CutRows cut nothing); no overlap anywhere in the die; all orientations row-legal |
| Not resynthesized / no buffering inside | final pnl | every N=22 carry net is exactly CO(i)→CI(i+1) (MSB: A1). The only extra cells in the adder name space are 5 free-placed `tiel` on the N=12 constant inputs (expected; see N7) |
| Pin access / routability | DRT and GRT logs | GRT overflow 0 on all layers (M2 46%, M3 53%, M4 2% in FIRM). DRT converges to 0 with no pin-access errors. Route DRC, Magic DRC and LVS are all 0 |
| Power hookup | metrics.json | PG violations 0, worst IR drop 0.059 mV (base 0.038 mV), LVS clean (VNW/VPW tied through DEF global connects) |
| Stale outputs | `gen_placement.py --check` (read-only) | FRESH |
| Raw metrics against tables | scraped `ra_*/runs/wokwi/final/metrics.json` myself | every number in the PLAN §2.2 table matches the raw metrics |

Evidence: `check_coords.py`, `check_coords.log`, `check_coords.json`, `contract_n22/`, `contract_n12/`,
`msb_arc_evidence.txt`, `netlen_compare.log` (all in this directory).

## 2. Findings

### B1 (BLOCKING): the MSB xor3_1 carries on its slowest input, and the plan reports the cost as noise

Evidence:
- Liberty `ss_125C_3v00`, xor3_1: A3→Z is about 0.3 to 1.5 ns. A1→Z and A2→Z are about 1.4 to 3.4 ns (my extract of the
  table entries). A3 is the late-arriving fast input. It also feeds only the last XOR stage, so a glitching carry on A3
  toggles fewer internal nodes than on A1.
- Measured on the ss worst path (`msb_arc_evidence.txt`):
  - `ra_hyb` (carry on A3): A3→Z = **1.597 ns**, WNS 26.12 ns;
  - `ra_final` (carry on A1): A1→Z = **3.545 ns**, WNS 23.69 ns;
  - `ra_final_fixed` (carry on A1): A1→Z = 3.585 ns, WNS 23.16 ns.
- hyb→final is **not** "one dangling net". The RTL diff also swaps the MSB pins (hyb `.A1(a) .A3(c)` → final
  `.A1(c) .A3(a)`). 1.95 ns of the 2.43 ns WNS difference is this arc. `hybcos` against `hyb` is bit-identical, so the
  flow is deterministic. The remaining difference is perturbation sensitivity, not randomness.
- Cause: `gen_placement.py:search_msb` minimizes only the HPWL proxy over 6 permutations. It overrode the default map
  `c_in: A3` (line 95) with `c_in: A1` (`out/placement_n22.json: msb_search`). "Assign interchangeable inputs by pin
  access" applies only to inputs that are timing- and energy-equivalent. The xor3 inputs are not.

Why it blocks: timing is the deciding cost of the cell path (PLAN §2.2, §3 condition 2). The delivered netlist is the
Phase 4 characterization input. As delivered, it carries an avoidable 2 ns penalty on the critical path, and the plan's
noise argument (§2.2 "Noise", §8 item 8) rests partly on this misattribution.

Exact changes:
1. `gen_placement.py:search_msb`: fix `c_in = "A3"` and search only the slide, the mirror and the a/b assignment over
   {A1, A2}. State the reason in a comment, with the Liberty arcs and the two measured values above. Keep the HPWL
   proxy as the tie-breaker within that constraint.
2. Regenerate `out/`, then confirm `--check` FRESH and `validate_placement.py` ALL_OK. Update the "MSB pin swapped"
   self-test to the new pin record. Rerun the frozen contract in gate mode for N=22 and N=12 into
   `contract_n22/` and `contract_n12/`.
3. PLAN.md:
   - §2.2 "Noise" bullet and §8 item 8: replace "differ only in one dangling net … 2.4 ns" with the correct
     attribution (MSB pin swap, 1.95 ns of the arc, cite both `max.rpt`). Say that the flow is deterministic
     (hybcos = hyb).
   - §0 / §2.2 / §8 item 2: give the timing cost as **−15.7 ns (hyb, carry on A3)**. Label final, final_mgp and
     final_fixed as including the A1 penalty.
   - §5.3: record the pin-equivalence rule.
4. tables.md: relabel `hybcos` from "(noise)" to "(determinism check: bit-identical to hyb)".

A new harden is optional. `hyb` is the measured carry-on-A3 netlist, so no chip conclusion changes.

### Non-blocking findings

**N1. Tap rule stated against the wrong limit.** PLAN §5.2 says "every row has a well tie within 18.5 µm". This library
is 5 V (MV): DF.13_MV and DF.14_MV allow at most **15 µm**. The column complies only because the staggered tap in the
well-sharing neighbour row is close. I measured a worst case of 10.3 µm per well. The same-row tap alone is up to
19.3 µm. The TT flow has `RUN_KLAYOUT_DRC` 0, and Magic does not check DF.13/14, so a clean flow run is not evidence
of compliance.
- Change the sentence to state the 15 µm rule and the neighbour-row argument.
- In Phase 4, run the KLayout deck (`feol=true`) at least on the block and once in chip context around the column.
- In whole-chip tetris, a column must never sit in a row whose well-sharing neighbour lacks the staggered tap.

**N2. "Only candidate whose chip harden area stays within noise" (§3) is false.** `addf1` (47,010.2 µm²) and
`final` (47,001.4) are also inside the band (46,819 to 47,221). The preference for the hybrid still holds on module
area and the MSB, but the stated reason should change.

**N3. The ~773 µm² "comes back as surrounding logic" is an estimate, not a measurement.** It subtracts a chip-level
shipped-flow delta from a module-level default-ABC delta: two different area measures. The cell-family diff supports
the mechanism (mux2 + clkinv for `neg`, tiel and tied-B addf for N=12), but the number should be labelled as an estimate.

**N4. On the recommendation's second half.** "The hybrid pays off only with mac_unit co-design" is justified as a
*necessary* condition. It is not shown to be *sufficient*. My upper-bound estimate, using Liberty areas only:
- the module-level saving is 876 µm² against default-ABC netlists;
- an addf chain cannot absorb `b = neg ? ~term : term`, so unless the inversion hides inside an existing term-mux cell,
  it costs at least 22 × xor2_1 = 580 µm²;
- N=12 specialization recovers about 156 µm², plus about 44 µm² of tie cells.

The best case is therefore roughly −0.3 to −0.5 k µm² (≤ 1% of std-cell area), comparable to the harden noise band,
for about −15.7 ns of ss slack. Energy is unproven: power is vectorless only, and vectorless power rose. Suggested
wording: "can pay off by at most ~1% area, only with co-design, and at a measured timing cost. The mac_unit phase must
show it on shipped-flow metrics." The mac_unit phase should also compare against a placement-only alternative that
keeps ABC's in-context mapping and only regions or clusters it. That keeps the operand merge and the timing.

**N5. Over-build and compaction.**
- (a) The `MANUAL_GLOBAL_PLACEMENTS` outputs (`out/chip_anchor_n*.json`) were measured to drift. Drop them, or mark them
  "do not use", so that nobody integrates with them.
- (b) `out/ripple_add_chip.v` with `` `ifdef SYNTHESIS `` is not needed while the shipped decision is "golden", and it
  fails the frozen contract's lint 8/68. Either switch it now to a dedicated define (PLAN §7.2) or park it until the
  mac_unit phase.
- (c) The stripe-free anchor list is a soft preference. M4 stripes cross every row in the chip, and every pin is on M1.
  Label it as soft so it does not shrink the tetris search space (128 against 272 anchors).
- (d) The column itself is not over-built. It sits at the bound: 716 of 726 site-rows (98.6%). It exactly fills a
  33-site tap window. I estimated the alternative grammar (2 bits per row in the 68-site in-row tap windows, which are
  staggered 35 sites per row): every second carry hop becomes about 20 µm. That is worse than the column's 6.7 µm mean
  routed hop. No compaction is available without changing the tap strategy, which PLAN §8.5 already notes.

**N6. Validator self-test gap.** The "anchor outside core" self-test is rejected by the tap-overlap check (row 38), not by
the outside-core check (`validation_run.log`), so the outside-core check is never exercised. Either test outside-core before
the tap check, or add a case that leaves the core without touching a tap (for example the block-coordinate placement
shifted one row above the block core, which has no taps).

**N7. N=12 tie cells are not part of the sub-placement.** The FIRM DEF has 5 `tiel` cells named
`core.mac.l_adder.*_6x`, PLACED by the tool and outside the column. This is harmless, but the composable sub-placement
is not self-contained until N=12 is specialized (PLAN §3.4).

**N8. Layout-controlled energy is small here, as the method predicts.**
- The column cut the N=22 carry wire from 359 to 140 µm (mean hop 17.1 → 6.7 µm, `netlen_compare.log`). That is −219 µm,
  or 0.4% of chip wire.
- The placeholder anchor added +1,658 µm on the adder's other nets and about +10 mm chip-wide.

This agrees with Agent 4's caution (§5.6). Placement of this block matters only together with its bit-slice neighbours.

**N9. Noise band reading.**
- The band has only two perturbation samples (n03, n04) plus the base, and the flow is deterministic.
- Timing: the −15.7 ns delta is about 3× the band width (4.7 ns). Robust.
- Area: "no gain" is robust; a gain cannot be claimed.
- Power: +0.2 mW above the top of the band, but vectorless.
- Cap count: 3 against at most 2 is not significant.

The conclusions in §2.2 are supported. Only the hyb/final attribution is wrong (B1).

**N10. Phase 4 block template, known deviations to state up front** (`out/block_n22_librelane.json`, marked untested):
- with `PDN_VPITCH` 38.87 and the default offset, a VPWR/VGND stripe pair lands at x ≈ 16.3 / 19.6 µm, **over the
  column** in a 27.44 µm die, unlike the stripe-free chip anchor. Rail via stacks will then sit inside the column, so
  block parasitics are not like-for-like with the chip anchor;
- the default `FP_TAPCELL_DIST` 20 will try to place taps inside the 37-site rows that the FIRM column occupies.

The plan handles both reactively (§7 step 2). Decide them in the template and record them as deviations.

## 3. Assessment of the chip-level conclusions (from the raw metrics)

| Claim | Raw evidence | Supported? |
|---|---|---|
| Synthesis gains at most 0.5% | 41,012.9 against 41,116.1 (−0.25%); synthesis noise −15 to +86 | yes |
| Harden area no better | 46,926.8 / 47,001.4 inside the 46,819 to 47,221 band | yes |
| ss WNS −15.7 to −22.6 ns | hyb 26.12, final 23.69, hyb22 19.20, against base 41.79 (band 38.2 to 42.9) | yes. The best correct netlist is −15.7 (B1) |
| Power +12% vectorless | 3.42 against 2.97 to 3.22 | yes (vectorless caveat stated) |
| MACRO_PLACEMENT_CFG holds std cells | 34/34 exact, FIXED, at every step DEF; taps unchanged | **yes, verified independently** |
| MANUAL_GLOBAL_PLACEMENTS drifts | final 32/34 exact, the two MSBs moved 17.9 and 20.7 µm | yes |
| RSZ_DONT_TOUCH_RX breaks repair | RSZ-3006 in `final_fixed_donttouch` logs | yes |
| Keep golden in the shipped chip | all of the above | **yes** |

## 4. Required changes (summary)

1. B1: constrain the MSB carry to xor3_1 A3, regenerate, revalidate, and rerun the gate-mode contract (N=22, N=12).
2. B1: correct the PLAN.md noise attribution and the timing-cost range, and relabel hybcos in tables.md.
3. Recommended, not blocking: N1 (tap rule wording, plus a KLayout DF.13/14 check in Phase 4), N2, N3 and N4 wording,
   N5a/b clean-up, N6 self-test, N10 template deviations.

After items 1 and 2 this review would be APPROVE.
