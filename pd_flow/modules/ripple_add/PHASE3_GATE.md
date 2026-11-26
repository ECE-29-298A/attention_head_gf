# ripple_add: Phase 3 gate (placement planning)

Date: 2026-11-26. Verdict: **PASSED.** Agent 5 approved in round 2 (`layout_review/REVIEW_ROUND2.md`)
after one blocking finding (B1) and ten non-blocking ones (round 1, `layout_review/REVIEW.md`).

## Plan (Agent 4, `layout_plan/PLAN.md`)
- Cell implementation for the tetris track: hybrid `addf_1` × (N−1) plus an `xor3_1` MSB, with the
  carry on A3, the fast input. Netlists are in `layout_plan/out/`. The frozen contract (hash
  `b879560878477abf`) passes in gate mode: N=22 10/10, N=12 11/11. The chip RTL with the cell
  branch behind a dedicated `RIPPLE_ADD_CELLS` define passes 68/68 with the define off.
- Placement: one bit per row, a column 33 sites (18.48 µm) wide. Bounding box: N=22
  18.48 × 86.24 µm (1,593.72 µm², 98.6% utilization); N=12 18.48 × 47.04 µm (869.30 µm²). This
  is at the area bound. Scripted by `gen_placement.py`, checked by `validate_placement.py` and
  independently by Agent 5's `check_coords.py` (22/22).
- Integration mechanism: `MACRO_PLACEMENT_CFG`, which keeps the cells FIXED at exact coordinates.
  It was verified on the chip with 34/34 cells fixed from step 17 to the final DEF, a
  buffer-free carry chain, and taps, endcaps and stripes identical to the baseline.

## Chip-level evidence (full harden, shipped config otherwise unchanged)
| Run | Std-cell µm² | ss setup WNS | Slew/Cap/Fanout | Power (vectorless) | DRC/LVS |
|---|---:|---:|---|---:|---|
| baseline | 46,819.2 | 41.79 ns | 381/1/11 | 3.050 mW | 0/0 |
| hybrid fixed column (A3), `chip_runs/fixed_a3` | 47,040.9 | 25.26 ns | 399/0/11 | 3.599 mW | 0/0 |

The orchestrator checked these numbers against the raw `metrics.json`.

## Decision (D3)
The golden RTL stays in the shipped chip. The cell-built adder gives no area gain at chip level
(std-cell area is inside the noise band), costs about 16.5 ns of ss setup slack, and adds
about 0.55 mW of vectorless power. ABC folds mac_unit's operand inversion, mux and constants
into the adder; a frozen block cannot absorb them. Any gain needs mac_unit co-design, which
Agent 5 bounds at about 1% chip area or less. The mac_unit phase must also compare against a
placement-only approach that keeps ABC's in-context mapping.

## Phase 4 scope
Standalone block implementation for evidence and characterization: fixed placement, automatic
routing, KLayout DRC including DF.13/14, LVS, extraction, ngspice post-layout checks, and views.
The chip integration is demonstrated by `chip_runs/fixed_a3` but not adopted in the shipped
configuration.
