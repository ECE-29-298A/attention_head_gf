# Whole-chip tetris: PLAN and record

**Objective (binding):** D10, `pd_flow/TETRIS_AREA_OBJECTIVE.md`: minimum shipped std-cell area
(`design__instance__area__stdcell`).
- Packing follows D8c.
- Timing (D6) and slew/cap/fanout (D2) are constraints, not objectives.

**User direction:** "place the whole chip at once". Every synthesized cell of the chip is placed in one placement:
datapath, divider, controller and SPI/config front end. There is no per-region or per-module placement.

**Method:** `/Users/samuelzhang/Desktop/HW_tetrising_ai/`, read in full:
- `tetris_layout_SKILL.md`
- `tetris_layout_method.md`
- `tetris_layout_routing-closure.md`
- `tetris_layout_experiments.md`

**Reused:** the datapath cluster's code (`pd_flow/clusters/datapath/scripts`), copied to `scripts/` and generalised to
the whole chip.

**Reproducibility:**
- Everything below can be regenerated from `scripts/`. Run directories are under
  `/Users/samuelzhang/ttharden/wc_work/<tag>_{r32,firm,cts,probe<k>}`.
- Numbers come from `results.json` unless another path is given. `record_wc_ref/` holds the first reference's record.

## 0. References and result

| Run | Path | Std-cell µm² | s/c/f | setup / hold min (ns) | wire µm |
|---|---|---:|---|---|---:|
| x0 (old shipping netlist) | `ttharden/md_x0_full/runs/wokwi` | 44,911.6 | 242/1/0 | 43.16 / 0.0069 | 49,125 |
| wc_ref (x0 + divider c06) | `ttharden/wc_ref/runs/wokwi` | 44,777.7 | 195/1/7 | 45.20 / 0.105 | 47,062 |
| **wc_ref2 (+ mac_unit c09), the reference** | `ttharden/wc_ref2/runs/wokwi` | **43,429.8** | **146/1/0** | 39.42 / 0.081 | 45,813 |
| wc_ref3 (+ mac_unit g2; rejected by the coordinator) | `ttharden/wc_ref3/runs/wokwi` | 44,446.2 | 96/0/0 | 40.41 / 0.092 | 48,247 |
| **ga1 (winner, signoff)** | `ttharden/wc_ga1/runs/wokwi` | **43,394.7** | **115/1/0** | 40.03 / 0.065 | 45,561 |

DRC, LVS and antenna are 0 in every row (route DRC, Magic DRC, LVS errors, antenna nets and pins).

**Area by class** (`baseline/*_area_classes.json`, `logs/wc_ga1_area_classes.json`):

| Class | x0 | wc_ref | wc_ref2 | ga1 | ga1 − wc_ref2 |
|---|---:|---:|---:|---:|---:|
| synth (synthesized masters) | 40,646.3 | 40,279.7 | 39,553.1 | 39,553.1 | 0 |
| upsize | 805.6 (49) | 779.3 (49) | 289.8 (28) | 289.8 (28) | 0 |
| repair | 671.7 (27) | 825.4 (32) | 746.4 (30) | 746.4 (30) | 0 |
| CTS | 759.5 (23) | 864.9 (33) | 812.2 (25) | **777.1 (24)** | **−35.1** |
| tap / endcap / tie | 1,527.9 / 342.5 / 158.1 | same | same | same | 0 |

- **wc_ref against x0: −133.9.**
  - Synth −366.6: c06 removes 7 divider flops, 57 → 50; the divider's Q-net flop count drops 88 → 81.
  - Upsize −26.3.
  - Repair +153.7.
  - CTS +105.4: 13 dummy loads against 3, explained in Step 9.
  - The expected ~44,545 assumed the synthesis delta alone; the flow overhead grew by 154 µm².
- **wc_ref2 against wc_ref: −1,347.9.**
  - Synth −726.6, upsize −489.5, repair −79.0, CTS −52.7.
- **Winner against wc_ref2: −35.1 µm², all clock tree.**
  - Slew drops 146 → 115, and wire drops 45,813 → 45,561 µm.
  - Signoff equals its dry run exactly (`wc_work/ga1_r32`).

## Method steps 1-12

### Step 1. Start at the neighbours
**Boundary.** The block is the whole 1×1 tile:
- die 346.64 × 160.72 µm, 39 rows × 607 sites;
- the TT DEF template's IO pins, PDN, 348 taps and 78 endcaps.

So the neighbours are the IO pins, the tap and endcap grid, and the clock entry: the `clk` pin, top right. They are
fixed points of the cost (`dplib.Wire.fixed`). There is no growth direction: the die is fixed and the objective is
std-cell area.

**Handoff.** The handoff to the flow is the **r32 relaxation** (Step 10). Steps 1–32 of the reference flow run
unchanged, then all 1,329 synthesized cells are fixed at the custom placement.

### Step 2. Expose the real graph
- **Graph:** the reference run's synthesized netlist, wc_ref2 `06-yosys-synthesis/*.nl.v`, sha16 `f2e8ad437dde2946`.
  It is parsed by `scripts/attribute.py` / `dplib.Design`.
- **Size:** 1,329 non-tie cells, 322 flops (all `dffq_1`) and 18 ties. Of these cells, 805 are structurally
  datapath (`attribute.py`, keyed by Q-net name and cone).
- **Movable set:** every cell. `--movable all` is the default of `gen_tetris.py`.
- **Netlist-agnostic:**
  - Instance names are never carried across netlists. Each reference run re-derives the seed, reservations,
    weights, CTS moves and baselines (`scripts/replay.py`).
  - The wc_ref placements were therefore discarded when the netlist changed (`record_wc_ref/`).
  - The datapath winner `xpk20_s1` was not transferred either: it is keyed to the x0 netlist.

### Step 3. Census the routing resources
Unchanged from the datapath census (`pd_flow/clusters/datapath/baseline/x0_census.json`):
- routing Metal2–Metal4: 2 vertical layers and 1 horizontal (horizontal is scarce);
- row = 7.00 Metal3 tracks;
- no cell master has Metal2 shapes.

The whole chip uses the same 30-odd masters, so the census was not re-run.

### Step 4. Choose a physical grammar
**Shipped grammar:** "tool placement + CTS-aware flop set + chip-wide weighted anneal".

The datapath grammar terms (bit slices, ring array, hinge targets) lost in the predecessor (+59, +17.6, +40/+70).
They were not repeated chip-wide.

**The new structural term is the clock-sink clustering** (Step 9). The flop positions are chosen by the real CTS,
in `scripts/cts_search.py`. The other 1,007 cells are placed for wires.

### Step 5. Bounds
**CTS bound.**
- 322 sinks with cluster size 20 force at least 17 leaves. Every run here uses exactly 17.
- Buffers alone: 3 clkbuf_8 + 17 clkbuf_4 = 693.6 µm².
- The leaves' total deficit is fixed at 17 × 20 − 322 = 18 flop pin caps. Each partial leaf gets one dummy, sized
  to its deficit. The cheapest split puts the whole deficit in one leaf (inv_12, 57.1 µm²). The level-1 imbalance
  of 10 vs 7 leaves costs one clkinv_4 (22.0 µm²).
- That gives about 772.7 µm². **ga1's 777.1 is within 4.4 µm² of this bound.** wc_ref2 has 812.2.

**Packing bound.**
- Placement-stage cells (synth + upsize + taps + endcaps + ties) total 41,871 µm², against the 49,561 µm² row
  extent of the seed. That is 84.5%; adding the flow's repair and CTS cells gives 87.6%.
- The die is fixed. A denser region only leaves whitespace elsewhere, and it counts only through the repair or
  CTS it changes (D10 §1).
- The datapath's pure-Tetris 95.9% bound did not route, so it was not repeated.

**Seed and converged packing (D8c).**
- Seed packing is 83.05% (`placements/s0/gen.json` `footprint`). Packing converged at **84.0–84.1%** (§G3).

### Step 6. Place for wires, then play Tetris
`dpo.py` is the legal-move annealer: relocate, same-width swap, flip, slide; legal by construction.

**Cost (D10 §2)**, the `genw.sh` recipe:
- Nets of drivers that the reference repaired or upsized: ×4.
- Those nets with seed HPWL ≥ 60 µm: ×30.
- Criticality weights from `crit.py` (`baseline/wc_ref2_crit.json`): 1 + 10·crit_rsz² + 5·crit_sig², where crit is
  the driver's closeness to its slew/cap/fanout limit.
- Optional chip-wide compaction `--pack-w` over all cells (`--pack-set all`).

**Movable cells:** all 1,007 non-flop cells. Flops stay frozen at the flop set chosen in Step 9, decided by
measurement in §G3.

**Flop moves** are explicit `--relocate cell:x:y` operations, recorded in `gen.json`:
- If a free gap lies within 4 µm of the target, the flop moves there.
- Otherwise a legal block swap moves the flop into the nearest run of whole cells that is at least its span, and
  packs those cells into its old span. Flops are never displaced, because a flop-for-flop swap leaves the sink set
  unchanged.

### Step 7. Emit one reproducible trial
**Generator and validator:**
- `scripts/gen_tetris.py` (+ `genw.sh`) writes `placement.json`, `macro_placement.cfg`, `reserve.json`,
  `manual_global_placements.json` and `gen.json`. `gen.json` records the arguments, log, footprint and netlist hash.
- `scripts/validate.py <dir> --regen` checks:
  - stale/regen byte identity;
  - that the views agree;
  - geometry (grid, orientation, overlap, taps);
  - intent;
  - the netlist hash;
  - LEF widths;
  - a planted-overlap self-test.
- Winner: `logs/validate_ga1.txt` → regen identical, 1,329 cells, OK. ga1_p1 and ga1_p2 also pass.

**r32 cfg:** `dplib.write_r32_cfg` emits the r32 MACRO_PLACEMENT_CFG, which gives each cell's x for its step-32
master; mirrored cells are right-aligned in their span. The dry run and the signoff use the same function.

**Placement cfg of the winner:** `macro_placement_ga1_r32.cfg` (= `placements/ga1/macro_placement_r32.cfg`).
`placement_ga1.json` holds the full placement.

### Step 8. Route with placement fixed
**Default handoff: r32.** In `dryrun.py --mode r32`, the chain starts from the reference's step-33 input. Step 33
(ManualGlobalPlacement) is replaced by ManualMacroPlacement (FIRM) of every synthesized cell. The flow then runs:
- 34 DPL (repair buffers only);
- 35 CTS;
- 37 resizer;
- 39–44 GRT, antenna, DRT;
- 54 RCX;
- 55 STA at 9 corners.

**Signoff equivalent** (`scripts/run_signoff.sh <tag> <dir> r32`):
- The mirror's `src/config.json` gets `MACRO_PLACEMENT_CFG` plus
  `meta {version 1, flow Classic, substituting_steps {Odb.ManualMacroPlacement: null, Odb.ManualGlobalPlacement: Odb.ManualMacroPlacement}}`.
- `version 3` is rejected: strict typing fails on the TT legacy config.
- src/, tt/ and the PDK are untouched.

**Mechanism check.**
- Full harden `wc_r32mech`, the tool's own step-34 placement through this path: 43,429.8, 151/1/0. That equals
  wc_ref2's area and matches the dry run `wc_work/s34_r32` exactly.
- check_held: 10 DEFs, ALL_HELD (`logs/check_held_r32mech.json`).

**Comparison handoff (M-FIRM, all cells FIRM at step 17):** the probe → reservation fixpoint of `pipeline.py`,
unchanged from the datapath.

**Containers:** at most 2 LibreLane containers machine-wide (`step_run_gated.sh`; the signoff waits as well).

### Step 9. Classify the failure with data
`area_classes.py`, `compare.py`, `cts_leaves.py` and `cts_tree.py` produced the following findings.

**FIRM at 17 costs, on wc_ref2:**
- +61.5 on the step-34 seed (`s34f`: upsize +61.5);
- +74.7 on the final seed (`s0`: upsize +61.5, repair +43.9, CTS −30.7).
- On wc_ref it cost +96.6 (`record_wc_ref`).
- Cause, as on x0: repair runs at legal positions instead of GPL positions.
- Chip-wide annealing under FIRM at 17 did not recover it: fa1 +61.5, fp20 +30.8.

**r32 removes the penalty by construction.** All 28 upsizes and 30 repair buffers of wc_ref2 are decided at step
32; nothing is resized after 32 in any run. Under r32 they are identical to the reference, and **the only
placement-dependent area is the clock tree**.

**CTS dummy loads (measured).**
- TritonCTS clusters the sinks (size 20, diameter 80) and builds a 2-level H-tree: root → 2 clkbuf_8 → 17 leaf
  clkbuf_4.
- It then inserts "dummy loads" (`clkload*`, inverters or buffers): every leaf whose clock-pin cap is below the
  largest leaf in its subtree gets one cell. Its input cap is the closest to the deficit, even for a 0.0001 pF
  deficit.
- wc_ref: flop `_2189_` was upsized to dffq_4 at step 32 (CLK cap 3.35 fF against 3.18 fF). It sat in a full
  20-flop leaf, so its 7 full siblings each got a clkinv_1: 61.5 µm². These are also the 7 fanout violations
  (20 flops + 1 dummy > 20).
- Moving that one flop out of the full cluster gave −61.5 on wc_ref (`c01f`/`c02f`), and fanout went 7 → 0
  (`record_wc_ref`).
- wc_ref2 has no high-cap flop. Its cost is the deficit split: leaves of 18/15/15/14 flops get
  clkbuf_4 + clkinv_4 + clkinv_4 + inv_4, plus the level-1 clkinv_4.

**Flop set chosen by the real CTS** (`cts_search.py`, `logs/cts_search_g{1,3}.json`):
- The tool's step-34 flop positions give 812.2.
- Its final flop positions, after CTS legalization, give 781.5 (13/14/15).
- One relocation (`_2062_` → (81.1, 21.5); it lands at (122.1, 15.7)) gives **777.1** (13/13/16 → inv_4,
  inv_4, inv_3).
- Most proposed moves leave the tree unchanged. Some make it worse (794.7, 799.1).

**Slew.** Under r32 the counts are measured at the final placement with GPL-decided buffers:
- the tool placement alone: 151–157;
- the weighted anneal: 98–137;
- the winner: 115 (wc_ref2 146).
- Cap is always 1. It is the same high-fanout split buffer as in the reference.

**Routing:** no candidate had route DRC or antenna violations.

### Step 10. Relax one degree of freedom at a time
Each relaxation was tried alone, zero-area first:
1. **r32 handoff** (fix the placement after step 32 instead of step 17). Zero area: reproduces the reference,
   **shipped**.
2. **Flop set** (CTS sink clusters), with everything else fixed. −30.7 / −35.1, **shipped**.
3. **Annealer seed** and **compaction weight** (D8c), on a fixed flop set. Slew only; area constant.
4. **Flops movable in the wire anneal.** −13.1 / −17.5: worse than a CTS-chosen flop set, **rejected**.

### Step 11. Finish the route
Signoff harden of the winner only: `scripts/run_signoff.sh ga1 placements/ga1 r32 /Users/samuelzhang/ttharden/wc_ref2`
writes `/Users/samuelzhang/ttharden/wc_ga1/runs/wokwi` (§G2.5).

### Step 12. Close the repeated object
**Not applicable as a tiled array:** the placement is the one 1×1 tile, with its own taps, endcaps, PDN and fill.
G4 is the full-tile harden.

## Gates

### G0 (function)
Placement only. The signoff netlist's sha256 equals wc_ref2's (`f2e8ad437dde2946cc8e…`). Function is the accepted
netlist's (c06 + c09, both formally accepted), and LVS 0 proves the layout matches it.

### G1 (inventory, legality)
- **Validator:** OK for ga1, ga1_p1 and ga1_p2 (Step 7).
- **Reservations:** r32 needs no probe. The 28 step-32 masters are placed directly; every one fits its span,
  which `write_r32_cfg` asserts. No cell was resized after step 32 in any run.
- **Held:** every r32 dry run held all 1,329 cells at every step DEF (`summary.json` `ALL_HELD`).

### G2 (fixed-placement route)
Route DRC 0 and antenna 0 for every candidate (`results.json`) and at signoff.

### G2.5 (stream-out, LVS)
Signoff run `/Users/samuelzhang/ttharden/wc_ga1/runs/wokwi`, from a copy of `wc_ref2` without runs/. The only
change is the copy's `src/config.json`: MACRO_PLACEMENT_CFG + meta.substituting_steps.
- **Signoff checks:**
  - Magic DRC 0, LVS 0, route DRC 0, antenna nets/pins 0/0;
  - Magic illegal overlap 0;
  - disconnected pins 9 (wc_ref2: 9);
  - manufacturability report: antenna, LVS and DRC passed (`signoff/wc_ga1_manufacturability.rpt`).
- **Held:** `check_held_run.py` gives 10 DEFs ALL_HELD, from ManualMacroPlacement (step 32 in r32 numbering) to
  final, with 28 resized cells (`logs/check_held_wc_ga1.json`).
- **Metrics:** `signoff/wc_ga1_metrics.json`. They are identical to the dry run `wc_work/ga1_r32`.

### G3 (area; D10)
**Gate:**
- area < 43,429.8;
- slew/cap/fanout no worse than 146/1/0, or inside the D2 noise band (381/2/13);
- setup and hold ≥ 0 at all 9 corners;
- route DRC 0 and antenna 0;
- held;
- no reservation miss.

`strict_d2` in `results.json` marks candidates that are at or below the reference on all three counts.

**Screens on wc_ref2** (dry run through step 55; Δ against wc_ref2):

| tag | what | area | Δ | ΔCTS | Δup / Δrep | s/c/f | hold ns | packing | gate |
|---|---|---:|---:|---:|---|---|---:|---:|---|
| s34 | tool step-34 placement, r32 | 43,429.8 | 0.0 | 0 | 0 / 0 | 151/1/0 | 0.076 | 83.1% | area (= ref) |
| s0r | tool final placement, r32 | 43,399.1 | −30.7 | −30.7 | 0 / 0 | 157/1/0 | 0.079 | 83.1% | pass (D2 band) |
| s34f | step-34 placement, FIRM at 17 | 43,491.3 | +61.5 | +8.8 | +61.5 / −8.8 | 146/1/0 | 0.083 | — | area |
| s0 | final placement, FIRM at 17 | 43,504.5 | +74.7 | −30.7 | +61.5 / +43.9 | 156/1/0 | 0.062 | — | area |
| fa1 | anneal, FIRM at 17 | 43,491.3 | +61.5 | 0 | +8.8 / +52.7 | 121/1/0 | 0.065 | — | area |
| fp20 | anneal + pack-w 20, FIRM at 17 | 43,460.6 | +30.8 | 0 | 0 / +30.7 | 113/1/0 | 0.086 | 83.8% | area |
| sa1..sa3 | s0 flops + anneal seeds 1–3, r32 | 43,399.1 | −30.7 | −30.7 | 0 / 0 | 98 / 128 / 137 /1/0 | ≥0.065 | 83.4% | pass |
| fm1, fm2 | anneal with flops movable, r32 | 43,416.7 / 43,412.3 | −13.1 / −17.5 | −13.2 / −17.6 | 0 / 0 | 118 / 104 /1/0 | ≥0.058 | 84.4% | pass, worse |
| g3b | s0 flops + `_2062_` relocation, no anneal | 43,394.7 | −35.1 | −35.1 | 0 / 0 | 151/1/0 | 0.079 | 83.1% | pass (D2 band) |
| **ga1** | **g3 flops + anneal seed 1 (winner)** | **43,394.7** | **−35.1** | **−35.1** | 0 / 0 | **115/1/0** | 0.065 | 83.5% | **pass, strict** |
| ga2, ga3, gp10 | seeds 2, 3; pack-w 10 | 43,394.7 | −35.1 | −35.1 | 0 / 0 | 123 / 128 / 117 /1/0 | ≥0.063 | 83.3–83.7% | pass, strict |
| rp_gp20, rp_gp40 | replay: pack-w 20, 40 on the g3 flops | 43,394.7 | −35.1 | −35.1 | 0 / 0 | 130 / 89 /1/0 | ≥0.074 (gp40) | see replay | pass, strict |

**Do flops move?** Decided by measurement:
- Letting the wire annealer move flops shrinks wire (43,259 µm) but changes the clustering at random. CTS lands at
  799.1 / 794.7.
- Choosing the flop set with the real CTS gives 777.1.
- So flops move **only** through CTS-scored relocations. A single flop moved in ga1.
- The leaf count stays 17 (the floor), so the gain is dummy loads, not buffers.

**Packing sequence (D8c).** s0 flop set, anneal seed 1, one weight at a time (`results.json` `packing_sequence`):

| tag | pack-w | packing | row-extent region µm² | dry-run area | s/c/f |
|---|---:|---:|---:|---:|---|
| s0r (seed) | — | 83.05% | 49,561.0 | 43,399.1 | 157/1/0 |
| sa1 | 0 | 83.35% | 49,356.9 | 43,399.1 | 98/1/0 |
| sp10 | 10 | 83.68% | 49,135.2 | 43,399.1 | 106/1/0 |
| sp20 | 20 | 84.04% | 48,909.1 | 43,399.1 | 119/1/0 |
| sp40 | 40 | 84.04% | 48,917.8 | 43,399.1 | 127/1/0 |
| sp80 | 80 | 84.12% | 48,863.0 | 43,399.1 | 115/1/0 |

- Area does not improve with tightening. Under r32, repair and upsizing are fixed, and with frozen flops CTS is
  fixed too. Density converges at **84.0–84.1%** from weight 20.
- Per D8c, tightening stops: the winner uses no compaction (pack-w 0, 83.5%), and gp10 (83.7%) gives the same
  area.
- The 322 frozen flops and the tap grid pin every row's extent. Freeing them costs CTS (fm1/fm2), so ~90% is not
  reachable without losing area. That stays a noted bound only.

**Robustness** (all must beat 43,429.8):

| variant | how | area | s/c/f | hold | gate |
|---|---|---:|---|---:|---|
| ga1 | winner | 43,394.7 | 115/1/0 | 0.065 | pass |
| ga1_p1 | re-anneal from ga1, T0 0.05, 20k it, seed 11 (41 cells, 0 flops) | 43,394.7 | 133/1/0 | 0.068 | pass |
| ga1_p2 | same, seed 12 (46 cells, 0 flops) | 43,394.7 | 129/1/0 | 0.061 | pass |
| ga1_j1 | two flops disturbed (`_2318_` ended 73 µm away) | 43,407.9 | 132/1/0 | 0.072 | pass, −21.9 only |

- **Passes.** The two perturbed variants and all 12 non-flop anneals on the two chosen flop sets give their
  set's area exactly. The area depends only on the flop set.
- **But the CTS part of the gain is sensitive to flop moves.** j1 falls back to −21.9, and the search saw
  outcomes from 777.1 to 799.1 for single-flop changes.

**Gain by class (signoff against wc_ref2):** repair 0, upsizing 0, CTS **−35.1** (812.2 → 777.1); synth, tap,
endcap and tie are 0.

**CTS detail** (`logs/wc_ga1_cts.json` against `baseline/wc_ref2_cts.json`):
- The same 3 clkbuf_8 and 17 leaf clkbuf_4.
- Dummies:
  - ga1: inv_4 ×2 + inv_3 + the level-1 clkinv_4, 83.4 µm²;
  - wc_ref2: clkbuf_4 + clkinv_4 ×2 + inv_4 + clkinv_4, 118.5 µm².

**Diagnostics (not objectives):**
- wire 45,561 µm vs 45,813 (−0.6%);
- vectorless power 2.975 mW vs 2.981 mW;
- IR drop 34 µV vs 40 µV.

### G4 (repeated object)
No tiled copies exist. The full 1×1 tile harden closes the object:
- taps 348, endcaps 78, fill 1,124, PDN;
- IR drop ran (`VSRC_LOC_FILES` unset, as in the reference);
- antenna 0, Magic DRC 0, LVS clean.

## Record: first reference wc_ref (c06 only), superseded
`record_wc_ref/results.json`, `record_wc_ref/summaries/`.
- FIRM at 17 cost +96.6.
- r32 on the step-34 seed reproduced wc_ref exactly.
- The dffq_4 relocation gave −61.5 (fanout 7 → 0). Six chip-wide anneals on it all gave 44,716.2 (−61.5), with
  slew 162–209.

On the coordinator's instruction these were not continued once the netlist changed to wc_ref2.

## Replay on a new netlist (one command)
`scripts/replay.py <reference run> <prefix> [--signoff]` re-derives, from the reference run only:
1. the baselines;
2. the r32 reproduction check;
3. the r32 screen of the tool's final flop set;
4. the CTS search;
5. the anneals and compaction sequence;
6. the gate and winner;
7. two perturbations;
8. optionally the signoff harden.

**End-to-end test on wc_ref2** (`logs/replay_rp.log`, `logs/replay_rp.json`; prefix `rp_`):
- the reproduction check gives 43,429.8;
- the s0 flop set gives 43,399.1;
- the CTS search independently finds the same relocation (`_2062_`, 777.1);
- the 12 anneals give 43,394.7 (g3 flops) or 43,399.1 (s0 flops);
- the winner `rp_ga1` is 43,394.7, 115/1/0, and **its placement.json is identical to ga1's**;
- its perturbations p1/p2 give 43,394.7.

One chain (`rp_gp40`) failed at launch: the step-42 container never started, no step log. Rerun, it gives
43,394.7 with **89/1/0**, the lowest slew at the winning area. It is a same-area alternative to ga1; ga1 had been
selected and signed off before that result.

## Risks and open items
- **Margin.** −35.1 µm² is about one or two dummy cells. The CTS part depends on the exact flop set. A disturbed
  variant gave −21.9, and single-flop moves ranged from −35.1 to +13.2 against the tool's final set. Any netlist
  change re-rolls it: re-run `replay.py`.
- **Wrong-way risk is bounded.** r32 with the tool's own step-34 placement is exactly the reference. The
  fallback (s0 flops) is −30.7, and every screened r32 candidate was at or below the reference.
- **The r32 handoff changes the flow's step list** (`meta.substituting_steps`) in the signoff copy's config.
  - It is not a src/ change, and the TT `tt_tool.py --harden` path accepts it: two full hardens.
  - It needs `meta.version 1`; version 3 is rejected by strict typing of the legacy config.
  - The submission flow must carry the same config lines.
- **Slew counts under r32** are measured with repair decided at GPL positions. They depend on the anneal: 98–157 on
  wc_ref2, all inside the band. The winner is strict, 115 ≤ 146.
- **Hold** is +0.065 ns, against the reference's +0.081.
- **Cap 1** is the reference's own, the same split buffer in every run.
- **Transient container launch failures:** 2 of about 75 dry-run chains (fa1 probe, rp_gp40) failed because a
  step container never started; there was no step log. Each was classified from the missing log and rerun clean.
  The flow is deterministic, so reruns are exact.
- **Bound left on the table:** about 4.4 µm² of CTS (the one-leaf deficit split) and the level-1 dummy; neither
  was pursued.
- **The datapath result `xpk20_s1`** (x0 netlist) is superseded. This placement covers all cells.
