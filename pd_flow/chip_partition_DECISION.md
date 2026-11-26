# Chip partition: A vs B comparison and decision (orchestrator, 2026-11-26)

Two architects worked independently (D7, user suggestion). The orchestrator checked their pilot
metrics against the raw `metrics.json`.

| Pilot | Std-cell µm² | Setup / hold min (ns) | Slew/cap/fanout | Wire µm | DRC/LVS/antenna |
|---|---:|---|---|---:|---|
| h2 (tool placement, reference) | 45,475.8 | 41.79 / 0.058 | 281/2/6 | 50,554 | 0/0/0 |
| A P1: h2 placement re-fed, all fixed | 45,493.3 | 41.66 / 0.054 | 252/2/6 | 50,604 | 0/0/0 |
| A P2: DIV packed to 90% | 45,467.0 | 41.34 / 0.075 | 386/2/6 | 61,917 | 0/0/0 |
| B p1: SPI block placed | 45,467.0 | 41.45 / 0.047 | 233/1/5 | 51,056 | 0/0/0 |
| B p2: all 1,416 cells, own annealer | 45,585.5 | 33.09 / 0.044 | 474/3/5 | 73,427 | 0/0/0 |

## Agreed by both
- Synthesis stays **flat**: every kept boundary costs area (mac +1,019, div +858, max_reg +652,
  exp_lut +463; all kept +2,568).
- Partition by placement into four groups: datapath (mac_unit, ripple_add ×2, max_reg, exp_lut),
  divider, controller, and SPI/config front end.
- The all-cells-fixed mechanism works at full chip scale and signs off clean.
- So far, from-scratch placement generators lose on wirelength against the tool (A +17% estimated,
  B +35% HPWL). Wire drives slew, and slew is the binding D2 constraint.
- Area custom placement can still recover on top of h2 is small:
  - B: 43 of 47 upsizes and 23 of 26 repairs recur in every placement tried; realistic 0–300 µm²
    (estimate).
  - A: at most about 2,489 µm² (estimate).

## Decision
1. **Flat synthesis with the four-group placement partition.** B's coordinates are the starting floorplan.
2. **Mechanism:** `MACRO_PLACEMENT_CFG` FIRM for all cells, with per-placement whitespace reserved for
   the resizer's in-place upsizes (B), or the cells pre-sized (A). Both must pass `check_held` at every step.
3. **Screening: B's dry run** (`chip_partition_b/scripts/pilot_dryrun.py --through 55`, about 2 min),
   which reproduced the p2 harden exactly. A full harden is only for Magic DRC/LVS signoff of a winner.
4. **Next experiment: tetris the datapath cluster, starting from the tool's placement and improving
   it.** It does not build a placement from scratch: bit-sliced S[21:0] columns are shared across
   mac/add22/max/exp, and the remaining cells keep their tool positions. The gate for each candidate
   is the dry run:
   - area < 45,475.8 µm²;
   - slew/cap/fanout ≤ 281/2/6;
   - setup and hold ≥ 0.
5. **Min-drive experiment** (keep logic at minimum drive; mux2_1 DRC test): runs in parallel. The
   winning configuration is combined with the tetris before any signoff harden.
