# ripple_add Phase 3: review round 2 (Agent 5)

Date: 2026-11-26. Re-verified Agent 4's revision 2 with my own checks. No Agent 4 file was edited, and nothing was committed.

## Verdict: APPROVE

## Checks

| Item | My check | Result |
|---|---|---|
| B1 in `out/` | read the netlists | `u_msb_x3 (.A1(b), .A2(a), .A3(c[N-1]))` for N=22, N=12 and the chip RTL. Generator `msb_search` gives `c_in: A3`; `--check` FRESH |
| B1 in the chip netlist | `ra_fixed_a3/runs/wokwi/final/pnl` | both `u_msb_x3.A3` driven by `core.mac.{adder,l_adder}.c[N-1]` |
| B1 effect | ss worst path, `max_ss_125C_3v00/max.rpt` | MSB arc A3→Z 1.647 ns (was A1→Z 3.585 ns in `final_fixed`) |
| fixed_a3 harden inputs | diff against `out/` | `src/ra_fixed.cfg` = `out/chip_anchor_n22.cfg` + `n12.cfg`; `src/ripple_add.v` = `out/ripple_add_chip.v`; `VERILOG_DEFINES` = `RIPPLE_ADD_CELLS`; `MANUAL_GLOBAL_PLACEMENTS` unset; the `chip_runs/fixed_a3` metrics copy is byte-identical to the run tree |
| fixed_a3 reported numbers | raw `final/metrics.json` | ss WNS **25.259 ns**, slew/cap/fanout **399/0/11**, 0 setup/hold violations, std-cell area 47,040.9 µm², route DRC / Magic DRC / LVS / PG 0. Matches the report |
| Coordinates and integration | `check_coords.py`, now parameterized (`FIRM=` run tree, MSB carry pin read from the netlist); `check_coords_round2.{log,json}` | **22/22 PASS** on the regenerated placement and in `ra_fixed_a3`. All 34 cells are FIXED at the exact location and orientation with the same master, at every step DEF from step 17 on. Taps, endcaps and stripes are identical to the baseline. No overlaps anywhere. Every carry net is CO→CI with the MSB on A3 and no buffers. The only extra cells are 5 `tiel`. Worst per-well tap distance is 10.3 µm |
| Contracts | Agent 4's `results.json` (`dut_sha256` = current `out/` hashes), plus my own reruns in `round2/` | `contract_n22` 10/10, `contract_n12` 11/11, `contract_chip_rtl` **68/68** (the dedicated define fixed the 8 lint items). My reruns give 10/10 and 11/11 |
| Validator | `validation_run.log` | ALL_OK. The outside-core self-test now hits the outside-core check (site 590). The width self-test hits the width check |

## N1–N10

| Item | Status |
|---|---|
| N1 tap rule | Done. PLAN states the 15 µm DF.13_MV/DF.14_MV limit and the neighbour-row argument, says Magic does not check it, and requires a KLayout DRC check in Phase 4 |
| N2 | Done. The claim is now "lowest synthesis area of the both-width frozen candidates; harden area does not separate it from addf_1" |
| N3 | Done. The 773 µm² figure is labelled an estimate |
| N4 | Done. Co-design is stated as necessary; the ≤ ~1 % upper bound and the placement-only alternative are cited in §3 |
| N5 | (a) `chip_anchor_n*.json` is marked "REFERENCE ONLY, do not use as MANUAL_GLOBAL_PLACEMENTS". (b) The `RIPPLE_ADD_CELLS` define replaces `SYNTHESIS`. (c) The stripe-free list is labelled a soft preference |
| N6 | Done (see the validator row) |
| N7 | Done (§8 item 9) |
| N8, N9 | Done. Noise text is corrected, the flow is deterministic, and the hyb/final gap is attributed to the pin swap. The tables relabel hybcos. N8 was an observation, so no change was needed |
| N10 | Done. `//deviation_1_pdn` and `//deviation_2_taps` are in the block template, and `FP_TAPCELL_DIST` is 100 |

## Remaining notes (non-blocking, no action needed for Phase 3)

- The search keeps the MSB mirrored with A3 on the west side. The carry hop proxy rose from 172 to 178 µm, which is
  negligible next to the 1.9 ns arc gain. Phase 4 may try the unmirrored slide if the carry hop matters.
- §5.4 now quotes a 13 % carry wire share, while §7 keeps a "≤ 12 %" target. Align the two numbers when Phase 4 updates them.
- The chip decision is unchanged: keep the golden RTL. Placing the column at the placeholder anchor still costs slew 399
  and about +9 mm of wire. Judge it only together with the mac_unit bit-slice.
