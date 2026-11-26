# Chip partition, floorplan and integration plan: Architect B

Rev 1, 2026-11-26. The work is in `pd_flow/chip_partition_b/`, the hardens in `/Users/samuelzhang/ttharden/cpb_*`,
and the step-level dry runs in `/Users/samuelzhang/ttharden/cpb_ortest/`. Every number below comes from a run
whose path is given. Estimates are marked **(estimate)**. Result labels: proven, bounded-pass, failed, timed-out,
unsupported, inconclusive.

## 0. Decision in one paragraph

**Synthesis stays flat and chip-wide (one ABC run).** Every RTL boundary that a separate synthesis unit would
freeze costs between +464 and +1,019 µm² (§1.1). The only exceptions are the 22-bit adder (−81) and the TT
wrapper (+136), and both are inside the ll_synth noise band (−52.7/+234.9). An exp_lut boundary with the Phase 2
candidate c08 measures −57.1, which is at the noise floor (§1.6).

**The placement partition is separate from the synthesis partition.** I attribute the flat netlist's cells to RTL
modules: 1,416 non-tie cells, all 329 flops matched, 0 mismatches (§1). Each cell is then placed in the region of
its cluster. There are four regions:

- `spi`: the isolated SPI/config wrapper;
- `ctrl`: the controller, flash SPI master and ties;
- `dp`: the coupled datapath, mac with both ripple_adds, max_reg and exp_lut;
- `div`: the divider.

**Integration mechanism M-FIRM.**

- `MACRO_PLACEMENT_CFG` lists every custom cell and makes it FIRM at step 17.
- GPL then places only the cells that are not listed. In the all-custom chip that is just the 18 ties.
- The space for in-place upsizing is reserved in advance. A standalone probe of steps 17-32 says which cells the
  resizer will upsize. For a given placement one probe was enough in 6 of 6 cases. A different placement needs
  its own probe: 2-4 new upsizes per re-seed.

**Evidence for the mechanism (all proven).**

- **Pilot harden p1, one block.** The SPI block at 89.2% packing: DRC-, LVS- and antenna-clean, 0 cells moved,
  −8.8 µm², which is inconclusive.
- **Pilot harden p2, the whole chip** (`/Users/samuelzhang/ttharden/cpb_p2`).
  - All 1,416 cells FIRM in floorplan B: 0 moved, and the 50 upsizes equal the 50 reservations.
  - Magic DRC, route DRC, LVS and antenna are all 0. Setup and hold are legal at all corners.
  - Every region reaches D8: spi 89.2%, ctrl 90.8%, div 90.0%, dp 86.0% (§4.5).
- **The dry run predicts the harden.** The standalone dry run of steps 17-55 reproduced p2 exactly: area,
  slew/cap/fanout, setup and hold. Cluster placements can therefore be judged without a harden.

**But my placements do not beat GPL (measured).**

- **p2 is rejected.** Its std-cell area is 45,585.5 against h2's 45,475.8 (+109.7 µm²). Its max_ss
  slew/cap/fanout of 474/3/5 against 281/2/6 fails D2.
- **The cause** is my quick annealing placer: HPWL is 35% above GPL's, which adds repair buffers and slew
  violations.
- **Other placements.** Three more custom placements gave +160 to +173 µm²: two re-seeds, and one unpartitioned.

**The upside is bounded.** Placement can change only the cells that PnR
inserts: in h2, 781.5 µm² of upsizing, 856.1 of repair buffers and 851.7 of clock buffers, 2,489.4 µm² in total
(5.5%). Measured, most of that does not move with placement:

- 43 of h2's 47 upsizes (698.1 µm²) recur with the same master in all four placements tried.
- So do the repairs on 23 of h2's 26 repaired drivers (781.5 µm² of repair in h2).

What remains is about 160 µm² outside the clock tree, plus the clock tree itself **(estimate**, §6). The tetrising
agents must make it up with structured placement that beats GPL on wirelength.

## 1. Connectivity analysis (deliverable 1)

**Method.**

- **Hierarchy-kept synthesis.** `SYNTH_HIERARCHY_MODE=keep` (tag `keep_all`), plus one
  `SYNTH_KEEP_HIERARCHY_MODULES` run per boundary, through LibreLane's own `Yosys.Synthesis` step
  (`scripts/ll_synth_b.sh`).
- **Configuration.** h2's merged config, so `EXTRA_EXCLUDED_CELLS` is applied the same way in every run.
- **Area.** Recomputed from each netlist with the full tt Liberty (`tools/netlist_area.py`), because stat.json
  leaves out the excluded masters. For example, flat stat.json gives 41,037.07, while the netlist, which is
  bit-identical to h2's, is 41,116.10.
- **Runs.** `/Users/samuelzhang/ttharden/cpb_synth/<tag>/runs/synth`, with results in `synth/results.tsv` and
  `synth/area_<tag>.json`.

### 1.1 Cost of keeping one boundary, chip total against flat (41,116.10 µm², netlist sha a339bf991497fc19)

| Boundary kept (tag) | Chip µm² | Δ against flat | In noise band? |
|---|---:|---:|---|
| everything (`keep_all`) | 43,684.48 | +2,568.4 | no |
| mac_unit (`k_mac`) | 42,134.67 | +1,018.6 | no |
| divider (`k_divider`) | 41,974.42 | +858.3 | no |
| ripple_add N=12 (`k_add12`) | 41,965.64 | +849.5 | no |
| max_reg (`k_maxreg`) | 41,768.07 | +652.0 | no |
| exp_lut (`k_explut`) | 41,579.28 | +463.2 | no |
| attention_controller, i.e. only the TT wrapper is separate (`k_core`) | 41,252.20 | +136.1 | yes |
| ripple_add N=22 (`k_add22`) | 41,034.87 | −81.2 | yes |

The costs do not add up. The singles sum to +3,897, against +2,568 for keep_all.

The max_reg cost (+652) reproduces the earlier "freezing cut ABC's cross-module optimization" failure mode, which
was about +550.

### 1.2 Module areas: hierarchy-kept against flat in-context

The hierarchy-kept areas are each instance's own cells from `synth/area_keep_all.json`. The flat in-context areas
come from attributing the h2 flat cells (`connectivity/h2_attribution.json`):

- flops are matched first by FSM state tables, then by Q name, then by RTL alias;
- combinational cells by 256-vector simulation signatures against the hierarchy-kept netlist;
- the rest by neighbour majority.

All 329 flops match. There are 0 primary-output mismatches, and all 318 checked D-functions agree.

| Instance | Kept µm² (cells, ff) | Flat in-context µm² (cells) |
|---|---:|---:|
| top (TT wrapper, SPI target, config chain) | 1,574.0 (54, 15) | 1,319.3 (32) |
| core (controller FSM, flash SPI master) | 5,863.4 (227, 41) | 6,212.4 (244) |
| core.mac (own) | 18,073.1 (477, 194) | 17,682.3 (507) |
| core.mac.adder (ripple_add 22) | 1,973.5 (86) | 1,525.7 (75) |
| core.mac.l_adder (ripple_add 12) | 1,062.5 (46) | 614.7 (29) |
| core.max_unit | 3,299.4 (123, 22) | 2,888.9 (121) |
| core.exponent_unit | 2,682.5 (108, 0) | 2,430.1 (96) |
| core.divider_unit | 9,156.2 (384, 56) | 8,284.7 (312) |
| ties | | 158.1 (18) |
| total | 43,684.5 | 41,116.1 |

Two notes on the flop matching:

- **The extra divider flop.** The flat divider has 57 flops because ABC names the ring-head flop Q after the
  divider's `magnitude[0]`, which equals `sum_in[0]`. The identity is recorded in
  `connectivity/fsm_tables.json:_extra_alias`.
- **FSM encodings.** Both FSMs are one-hot in the flat netlist. The divider is binary when kept.

### 1.3 Inter-module connections

**Hierarchical port widths** (`connectivity/hier_ports.json`), in bits from driver to sink:

| Driver → sink | Bits |
|---|---:|
| mac→div (O0 20 + L 12) | 32 |
| mac→max (S) | 22 |
| mac→exp (S→D) | 22 |
| max→mac (M) | 22 |
| core→mac (control) | 21 |
| top→core | 12 |
| exp→mac (W) | 8 |
| core→top | 7 |

The divider drives only `result[11]`, which becomes `out_bit`, plus done. The other 12 output bits are unused.

**Flat nets between modules** (h2 netlist, `flat_pair_nets`), in nets and sink pins:

| Module pair | Nets | Sink pins |
|---|---:|---:|
| add22↔mac | 77 | 111 |
| ctrl↔mac | 50 | 90 |
| div↔mac | 45 | 83 |
| max↔mac | 44 | 69 |
| exp↔mac | 37 | 62 |
| ctrl↔max | 18 | 18 |
| add12↔mac | 18 | 21 |
| ctrl↔top | 15 | 23 |
| ctrl↔add22 | 12 | 12 |
| add12↔exp | 10 | 14 |
| top↔exp | 5 | 40 |
| ctrl↔div | 8 | 33 |
| top↔mac | 1 | 2 |

**Between floorplan regions** (`connectivity/region_pair_nets.json`), in nets and sink pins:

| Region pair | Nets | Sink pins |
|---|---:|---:|
| ctrl↔dp | 85 | 130 |
| div↔dp | 45 | 83 |
| ctrl↔spi | 15 | 23 |
| ctrl↔div | 8 | 33 |
| spi↔dp | 6 | 42 |
| pins↔ctrl | 28 | 70 (18 of them are tie nets) |
| pins↔spi | 6 | 20 |

**Shared and high-fanout signals** (fanout, then the modules it reaches):

| Net | Fanout | Sinks |
|---|---:|---|
| clk | 329 | mac 194, div 57, ctrl 41, max 22, top 15 |
| `_0492_` (max_reg enable) | 44 | |
| `_0705_` (mac) | 39 | 2 of them in exp |
| `_0539_` (div) | 32 | |
| `core.divider_unit.state[0]` | 30 | |
| `_0592_` (ctrl) | 29 | 13 of them in div |
| `config_chain[7]` (score_shift[3]) | 19 | 15 of them in exp |

`config_chain[7:4]` drives 38 exp_lut sink pins in total, all coming from the SPI block.

### 1.4 Where h2 put each module

From `connectivity/h2_landing.svg`. Here, fill is the cell area over the module's bounding box. "Same-label
neighbours" is the fraction of a cell's 6 nearest neighbours that belong to the same module.

| Module | Bounding box (x0, y0, x1, y1) µm | Fill | Same-label neighbours |
|---|---|---:|---:|
| mac | 4–334 × 4–157 (whole core) | 0.35 | 0.63 |
| div | 24–342 × 8–157 (rms x 95 µm) | 0.17 | 0.75 |
| top (SPI) | 120–315 × 67–157 | 0.08 | **0.24** |
| ripple_add 22 | 55–185 × 16–145 | 0.09 | **0.31** |

GPL scatters the small modules, top and the adders, through mac.

### 1.5 PnR-inserted area by module in h2

From `tools/repair_attrib.py` (`area/h2_pnr_by_module.json`):

| Module | Upsizing µm² | Repair buffers µm² |
|---|---:|---:|
| controller | 278.8 | 223.9 |
| mac | 197.6 | 267.8 |
| **top (SPI)** | 92.2 | 149.3 |
| div | 70.3 | 149.3 |
| exp | 68.1 | |
| add22 | 35.1 | |
| add12 | 24.2 | |
| max | 15.4 | 65.9 |

The SPI wrapper is 3% of the logic but 15% of the repair and upsizing. That cost comes from its long outgoing nets
(cs_rise, config_chain to exp).

### 1.6 exp_lut boundary with the Phase 2 candidates (coordinator note)

Same flow, measured (`synth/area_k_explut+c08.json` and the matching files):

| RTL | Boundary | Chip µm² | Δ against flat golden | exp_lut own µm² | Rest µm² |
|---|---|---:|---:|---:|---:|
| golden | kept | 41,579.28 | +463.2 | 2,682.5 | 38,896.8 |
| c08 | kept | 41,059.02 | **−57.1** | 2,114.0 | 38,945.0 |
| c10 | kept | 41,315.86 | +199.8 | 2,370.8 | 38,945.0 |
| c08 | flat | 42,046.86 | +930.8 (reproduces OPTIMIZATION.md) | | |
| c10 | flat | 41,133.66 | +17.6 (reproduces OPTIMIZATION.md) | | |

c08 behind a kept boundary is a single sample 4.4 µm² beyond the band's lower end (−52.7). That is
**inconclusive**, and far from the ~400 µm² a harden can confirm.

A kept exp boundary costs the rest of the chip +210 to +259 µm². For it to pay measurably, a module-level exp_lut
would have to come in under about 1,770 µm² **(estimate)**. Decision: keep exp_lut flat. Revisit if exp_lut
Phase 2 reaches that.

## 2. Partition (deliverable 2)

| Region | Kind | Flat cells (ff) | Synthesized µm² | Synthesis boundary | Why |
|---|---|---:|---:|---|---|
| `spi` | isolated block | 32 (15) | 1,319.3 | none (flat) | No shared logic. It talks to ctrl over 15 nets and drives score_shift to exp. Keeping the wrapper separate costs +136 (noise), so there is no reason to cut ABC. |
| `ctrl` | control cluster | 244 (41) + 18 ties | 6,370.5 | none | FSM, counters and flash SPI master. It is the hub for mac control (50 nets) and sits under the flash pins. |
| `dp` | coupled datapath cluster | 828 (216) | 25,141.6 | none | mac with adder 22, adder 12, max_reg and exp_lut. They exchange 77+44+37+18 nets. Freezing any of them costs +463 to +1,019, except adder 22 at −81 (noise). |
| `div` | placement region | 312 (57) | 8,284.7 | none | 45 nets to mac (O0 and L) and 8 to ctrl; its 1-bit result goes to uo_out[0]. Kept, it costs +858. |

**Boundary ports.** Placement ports are not synthesis ports. They are the region crossings, with buses kept in bit
order so that both sides line up.

- **spi**
  - North: ui_in[2:0], rst_n, clk and ena pins, at x 302-339.
  - West, to ctrl: start/out_ready (cs_rise), out_shift, last[3:0] and cont. idle comes back from ctrl.
  - South-west corner, to dp/exp: score_shift[3:0], fanout 38.
- **ctrl**
  - North: flash pins uio_oe[1] (x 76.4), uio_out[3,1,0] (x 120-142), uio_in[5,4,2,1] (x 222-251) and
    uo_out[1] drdy (x 192.9). Row 38, under the 18 unused-output pins (x 33-186), takes the ties.
  - East: spi.
  - South, to dp: the mac control bundle (accum_mode, load, subtract, score_en, first, accum_en, sel[2:0],
    bit_sel[2:0]), q[7:0] and the serial nibble data (`v`/`ki`), ordered west to east to match mac's input
    columns.
  - South-east, to div: start and shift.
- **dp**
  - North: ctrl.
  - North-east corner, at exp: score_shift.
  - East, to div: O0[19:0] and L[11:0], LSB at the south, along x = 276.64.
  - Inside dp: S[21:0] runs from mac's S register to max S_in, exp D and adder 22, in the same bit order.
- **div**
  - West: O0 and L.
  - North-west corner (x 198-205, rows 30-33): result[11] to uo_out[0] at x 200.2.
  - North: ctrl handshakes.

## 3. Floorplan B (deliverable 3)

- **Spec:** `floorplan/floorplan_spec.json`.
- **Evaluation:** `tools/floorplan.py`, output in `floorplan/floorplan_eval.json`.
- **Drawing:** `floorplan/floorplan_b.svg`, from real coordinates: the 39 rows, all 348 taps and 78 endcaps from
  the h2 DEF, and the TT pins.

**Tile constraints.**

- Rows sit at y = 3.92 + 3.92·r, with sites at x = 3.36 + 0.56·k.
- Endcaps take sites 0-1 and 605-606, so placeable x runs from 4.48 to 342.16.
- Taps:
  - rows 0 and 38: every 34 sites, from site 34;
  - odd rows: at 70·k;
  - even rows: at 35 + 70·k.
- Rows alternate N/FS, and cells take their row's orientation.

**Expected area.** Each region's expected cell area is its synthesized area plus its h2-attributed PnR reserve:
upsizing, repair buffers, and the CTS area split by flop count (§1.5).

| Region | Rectangles (µm) | Area µm² | Taps µm² | Synthesized | Reserve (upsizing / repair / CTS) | Packing, synthesized + taps | Packing, expected | Measured in p2, all non-fill cells + taps |
|---|---|---:|---:|---:|---|---:|---:|---:|
| spi | 237.44-342.16 × 137.20-152.88 (rows 34-37) | 1,642.0 | 52.7 | 1,319.3 | 92.2 / 149.3 / 38.8 | 83.6% | 89.2% for the block's own cells after upsizing, measured in p1. Its repair and CTS cells land in ctrl/div. | 89.2% |
| ctrl | row 38 full width; rows 34-37 × 4.48-237.44; rows 30-33 × 4.48-198.24 | 8,014.7 | 250.3 | 6,370.5 | 278.8 / 223.9 / 106.1 | 82.6% | 90.2% | 90.8% |
| div | rows 30-33 × 198.24-342.16; rows 0-29 × 276.64-342.16 | 9,961.8 | 338.1 | 8,284.7 | 70.2 / 149.3 / 147.6 | 86.6% | 90.2% | 90.0% |
| dp | rows 0-29 × 4.48-276.64 | 32,006.0 | 886.9 | 25,141.6 | 340.3 / 333.7 / 559.2 | 81.3% | 85.2% | 86.0% |

**Soft sub-regions inside dp** guide the tetrising agent:

- **max**: north-west, next to mac's S and M;
- **exp**: north-east, where score_shift enters, next to div;
- **mac with both adders**: the rest. The S bit-slices run east-west.

**Budget against the 51,967 µm² core.**

- Placeable area is 51,624.5; the endcaps take 342.5.
- The regions tile all of it.
- At h2 reserves, the expected std-cell area is 45,475.9 (h2's total, by construction).
- Unassigned area is 0.

The h2 chip as a whole is already at 87.5% utilization. So 90% regions can only free about 1,900 µm²
**(estimate)**: the gap between 90% and 87.5% on the placeable area. That is also why dp sits at 85.2%.
Every µm² of inserted area that custom placement removes becomes free tile area.

**Clock.** The clk pin is at x 331.2, top right. There are 329 sinks, 216 of them in dp. The CTS reserve is h2's
22 clkbuf + 9 clkinv = 851.7 µm².

**Pins.** All TT pins are Metal4 on the top edge, and the pin locations are fixed by the TT DEF template. The used
pins sit above ctrl and spi, as listed in §2.

## 4. Integration mechanism (deliverable 4)

### 4.1 What LibreLane 3.0.14 does

From the source in the image: `flows/classic.py`, `steps/odb.py`, `scripts/odbpy/placers.py`,
`scripts/openroad/{gpl,repair_design,dpl,cts}.tcl` and `common/resizer.tcl`.

- **Step 17, `Odb.ManualMacroPlacement`.** It reads `MACRO_PLACEMENT_CFG` (lines of `inst x y orient`), accepts
  std-cell instances, gridifies to 5 dbu and sets them **FIRM** (`--fixed`).
- **Steps 18-19.** CutRows and TapEndcapInsertion ignore FIRM std cells. Measured: rows, taps and endcaps were
  identical to h2's step 19 (`cpb_ortest/p1/early`).
- **Steps 24/28, GPL.** It skips when everything is FIXED/FIRM. Otherwise it places only the movable cells; in
  the all-custom chip, "Movable instances: 18", which are the ties.
- **Step 32, `RepairDesignPostGPL`.**
  - It runs `repair_design`, then `repair_tie_fanout`, which re-creates the 18 ties under new names, then DPL.
  - `repair_design` **resizes FIRM cells in place**. If the larger master overlaps a fixed neighbour or a tap,
    DPL fails with DPL-0033.
  - DPL places every inserted buffer and tie in the whitespace and does not move FIRM cells.
- **Step 33, `Odb.ManualGlobalPlacement`.** It sets PLACED. It runs after step 32's DPL, so it is too late to
  enable legalization.
- **Step 35, CTS.** It legalizes its own buffers with DPL.
- **Step 37.** Hold repair inserts buffers and does not resize; there are no setup violations.

### 4.2 Tests

All of these are standalone steps on h2's own step inputs (`scripts/step_chain.py`, `scripts/pilot_dryrun.py`), not
hardens.

| Test | Setup | Result | Label |
|---|---|---|---|
| T1 | all 1,434 FIRM at their GPL positions | DPL-0006, site alignment failed on 1,416 cells | failed (expected: positions must be legal) |
| T1b | all FIRM at h2's final legal positions, no dont_touch | repair resized 48 cells, then DPL-0005 with 25 overlaps (e.g. `_1248_` oai31 growing into TAP_TAPCELL_ROW_12_189) | failed: **upsizing hazard reproduced** |
| T2 | T1b plus `RSZ_DONT_TOUCH_LIST` = all instances | ODB-1211 "load pin is dont_touch, cannot insert a buffer", then RSZ-3006 hard error | failed: dont_touch is **unsupported** as a shield |
| M-PLACED | spi FIRM through GPL, then `MANUAL_GLOBAL_PLACEMENTS` moved before step 32 (PLACED, same positions) | the flow passes, but GPL cells inside the block's whitespace push it apart: 23/32 cells moved (mean 11.1 µm, max 59.9) and 24 mirrored | bounded-pass (works, drifts) |
| **M-FIRM** | spi FIRM plus reservations: the 6 upsizes predicted by the dry run (nand4_1→4, dffq_1→2/4, buf_1→3) | steps 17-37 pass; the same 6 upsizes, all within their reservations; 0 moved, 0 mirrored | **proven** |
| M-FIRM, full chip | all 1,416 non-tie cells FIRM (`placements/chip_v1r`): placed by my region placer into floorplan B, plus 55 reservations from a probe run | steps 17-37 pass. GPL moves only the 18 ties. 54 upsizes, all reserved. 0/1,416 moved. Repair, CTS and hold cells all legal. Packing 87.8% at step 37. | **proven** (mechanism at full scale) |
| M-FIRM, full chip, through signoff | `placements/chip_v2r`: 1,416 FIRM, 50 reservations; dry run of steps 17-55, then harden p2 | dry run and harden agree exactly (area, slew/cap/fanout, setup, hold). DRC, LVS and antenna 0. 0/1,416 moved. | **proven** (§4.5) |

**The reservation loop.**

1. Probe with `pilot_dryrun.py --probe`, so that DPL can legalize and the resizer's decisions become visible.
2. Reserve exactly those cells (`region_place.py --reserve`, width taken from the target master).
3. Run a FIRM dry run and check that the resized set is contained in the reserved set.

For a given placement, one probe was enough in all 6 cases: spi_p1, chip_v1r, chip_v2r, onecore_v5 and the two
re-seeds. Resizer decisions depend only on positions and loads, not on placement status, so the probe and the
FIRM run agree.

A reservation does **not** carry over to a different placement.

- Re-seeding chip_v2r (seeds 2 and 3) kept the 50 old upsizes, added 2 and 4 new ones, and widened one cell
  (`_1905_` nand4_2 → nand4_4).
- The FIRM runs with the old reservation failed loudly with DPL-0033.
- The fix was to probe each re-seeded placement, reserve the union (widest master), re-legalize with `--keep-rows`,
  and re-run. That converged (52/52 and 54/54).

A non-converging case always fails loudly with DPL-0033, never silently.

**Flop renumbering** is handled by `tools/remap_placement.py`. Flops are matched by the public name of their Q net;
combinational cells by iterative structural matching (same master, same pin to the same already-matched driver).

- **Synthetic renumbering** (every instance name permuted): 329/329 flops and 1,416/1,416 non-tie cells mapped,
  0 wrong.
- **A genuinely re-synthesized netlist** (`flat+c10`, a different ABC result): 329/329 flops, 658/1,474 cells.
  The other 798 must be re-placed, seeded from the carried cells.

Placements therefore have to be generated against the frozen netlist. The sha is checked in every run.

### 4.3 Pilot harden p1: one isolated block at about 90% (harden 1 of 2)

**Setup.**

- Run: `/Users/samuelzhang/ttharden/cpb_p1`, an h2 copy plus `MACRO_PLACEMENT_CFG` (`scripts/run_pilot.sh`).
- Placement: `placements/spi_p1`, generated by `tools/region_place.py` and checked with `tools/check_place.py`.
- The synthesized netlist is bit-identical to h2 (a339bf991497fc19).

**Placement result.**

- In the final DEF, all 32 cells are FIXED at their exact positions: 0 moved, 0 mirrored.
- 6 masters were upsized, all within their reservation.
- Block packing is 83.6% before the flow and **89.2% after upsizing** (cells + taps over the region).
- The region as a whole is at 97.5%, because the GPL cells of the rest of the chip fill its remaining whitespace.

**Signoff.**

- Magic DRC 0, route DRC 0.
- LVS 0 errors, 0 unmatched devices, 0 unmatched nets.
- Antenna 0, illegal overlap 0.
- Slew/cap/fanout 233/1/5 against h2's 281/2/6, so within the D2 band.
- Setup WNS 41.45 ns; hold +0.047 ns at max_ff (h2 +0.058). All corners ≥ 0.

**Area.** **45,467.0 against 45,475.8 µm² (−8.8): inconclusive.**

| Class | p1 µm² | h2 µm² |
|---|---:|---:|
| Upsizing | 781.5 | 781.5 (unchanged) |
| Repair buffers | 886.9 | 856.1 |
| CTS | 812.2 | 851.7 |

The block's own upsizing and repair are the same as in h2. They are set by its long nets to cells that GPL placed,
which is the second failure mode (the neighbours) seen from the other side. The gain has to come from placing the
neighbours together (D7).

- **Review page:** `pd_flow/review_artifacts/chip_partition_B_spi_p1.html`.
- **Spec:** `review/chip_partition_B_spi_p1.json`.

### 4.4 Full-chip custom placement: what my quick placer reaches

All placements below are legal (0 validator errors). The metric is HPWL of every signal net, clock excluded, from
`tools/hpwl.py`. **h2's final placement gives 40,659 µm.**

| Placement | HPWL µm | Against h2 |
|---|---:|---:|
| h2 GPL positions, re-legalized by my row packer only | 80,064 | +97% |
| one region (whole core), SA v1, 400k moves | 50,465 | +24% |
| one region (whole core), SA v2 (targeted moves), 400k | 43,375 | +6.7% |
| one region, SA v2, re-placed with reservations (`onecore_v5`) | 43,204 | +6.3% |
| floorplan B, four regions, SA v1 (`chip_v1`) | 55,465 | +36% |
| chip_v1 with the reservations re-legalized (`chip_v1r`) | 60,259 | +48% |
| floorplan B, SA v2, 2 passes (`chip_v2`) | 53,200 | +31% |
| chip_v2 re-placed with reservations (`chip_v2r`, hardened as p2) | 55,032 | +35% |

chip_v1r at step 37 (dry run, against h2 at step 37):

| Class | chip_v1r µm² | h2 µm² | Δ |
|---|---:|---:|---:|
| Upsizing | 882.5 | 781.5 | +101 |
| Repair buffers | 922.0 | 856.1 | +66 |
| CTS | 895.6 | 851.7 | +44 |
| **Total** | | | **+211** |

So a placement that is 48% longer than GPL costs only +211 µm² of inserted area. The inserted area is not very
sensitive to wirelength in this design. Most of it is fanout and slew repair on logically high-fanout nets.

**Full-chip FIRM dry runs through post-route STA.** These are standalone steps 17-55, including RCX and the
9-corner STAPostPNR (`scripts/pilot_dryrun.py --through 55`, about 2 minutes), each run after a probe and its
reservations. In all of them:

- the resized set equals the reserved set;
- 0 cells moved;
- GPL moved only the 18 ties;
- rows, taps and endcaps are identical to h2's.

The runs are under `/Users/samuelzhang/ttharden/cpb_ortest/`: `onecore_v5_sta`, `chip_v2r_sta`, `chip_v2r_s2b_sta`
and `chip_v2r_s3b_sta`. The seed-2 and seed-3 runs are the same placer and floorplan with different seeds.

| | h2 | onecore_v5 (one region) | chip_v2r (floorplan B, seed 1 = p2) | chip_v2r seed 2 | chip_v2r seed 3 |
|---|---:|---:|---:|---:|---:|
| HPWL µm | 40,659 | 43,204 | 55,032 | 55,406 | 56,309 |
| Routed wirelength µm | 50,554 | 59,744 | 73,427 | 76,089 | 77,261 |
| DRT DRC / antenna nets | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Upsizing µm² | 781.5 | 893.5 | 821.0 | 884.7 | 906.6 |
| Repair buffers µm² | 856.1 | 908.8 | 965.9 | 943.9 | 943.9 |
| CTS µm² | 851.7 | 847.4 | 812.2 | 829.8 | 812.2 |
| **Std-cell area µm²** | 45,475.8 | 45,636.0 (+160.2) | **45,585.5 (+109.7)** | 45,644.8 (+169.0) | 45,649.2 (+173.4) |
| Slew / cap / fanout (D2: ≤ 281/2/6) | 281/2/6 | 308/4/9 | 474/3/5 | 513/3/3 | 485/3/4 |
| Setup / hold WNS ns | 41.79 / +0.058 | 38.31 / +0.090 | 33.09 / +0.044 | 32.80 / +0.081 | 29.76 / +0.100 |

Region packing of chip_v2r at step 44 counts every non-fill cell, inserted ones included:

| Region (pieces) | Packing |
|---|---|
| spi | 89.2% |
| ctrl | 88.4% / 94.5% / 87.3% |
| div | 92.9% / 89.2% |
| dp | 86.0% |

DRT was clean at these densities, so D8 routability is **proven** at step level.

**Area: worse than h2 in all four, by 110 to 173 µm².**

- **Determinism.** For a fixed netlist and placement the flow is deterministic: the dry run reproduced harden p2
  exactly. So the comparison noise for placement work is not the ~400 µm² measured across synthesized netlists.
  It is the spread between placements of equal quality: 63.7 µm² over three seeds (n = 3).
- **D2 fails in all four.** The slew counts are 308 to 513 against h2's 281, and the cap counts 3 or 4
  against 2.

**Wirelength, inserted area and slew.**

- **Wirelength.** The three floorplan B placements are 23 to 29% longer in routed wire than the unpartitioned
  one.
- **Area.** Their std-cell area differs from it by −50.5, +8.8 and +13.2 µm². That is inside the seed spread,
  so the partition's area effect is **inconclusive**.
- **Slew.** Their D2 slew counts are clearly worse: 474 to 513, against 308 unpartitioned. Slew tracks
  wirelength, and area mostly does not.

**Comparison.** Neither my partitioned nor my unpartitioned quick placement beats GPL+DPL on inserted area.

**What the tetrising agents have to beat:** h2's inserted 2,489.4 µm².

- My quick placements insert 2,599.1 (chip_v2r), 2,649.6 (onecore_v5), 2,658.4 (seed 2) and 2,662.8 (seed 3).
- The levers, from these runs:
  - region-clustered flops already shrink the clock tree, by −22 to −40 µm² in the three floorplan B runs;
  - the losses are repair on long control and bus nets (+88 to +110 µm²) and upsizing (+40 to +125 µm²).

### 4.5 Pilot harden p2: the whole chip custom-placed (harden 2 of 2)

**Setup.**

- Run: `/Users/samuelzhang/ttharden/cpb_p2`, 11:03:21-11:04:48. It is h2 plus the one config line
  `MACRO_PLACEMENT_CFG`, with 1,416 FIRM cells.
- Placement: `placements/chip_v2r`, i.e. spi_p1, then dp, ctrl and div by `tools/chip_place.py`, with 50
  reservations.
- The netlist is bit-identical to h2.

**Placement result.**

- In the final DEF, all 1,416 cells are FIXED: 0 moved, 0 mirrored.
- 50 master changes, equal to the 50 reservations.
- GPL moved the 18 ties only.

**Signoff.**

- Magic DRC 0, route DRC 0.
- LVS 0 errors, 0 unmatched devices, 0 unmatched nets.
- Antenna 0, illegal overlap 0.
- Setup WNS 33.09 ns, hold +0.044 ns (max_ff); all 9 corners ≥ 0.
- Power 3.147 mW (h2 2.934).
- **D2 failed:** slew/cap/fanout 474/3/5 against 281/2/6.

**Area.** 45,585.5 against 45,475.8 µm² (**+109.7**), with upsizing +39.5, repair buffers +109.8 and CTS −39.5.
By module (`area/p2_pnr_by_module.json`, compared with h2 in §1.5):

- The controller rose by +30.7 µm² of upsizing and +74.7 of repair; mac by +8.8 and +13.2.
- exp_lut gained 22.0 µm² of repair.
- All other modules are unchanged to the 0.1 µm².

**Region packing in the final DEF** (all non-fill cells plus taps, over the region):

| Region | Packing |
|---|---:|
| spi | 89.2% |
| ctrl | 90.8% |
| div | 90.0% |
| dp | 86.0% |
| whole placeable core | 87.6% |

So D8 is met, and routability at that density is shown by a clean DRT and signoff.

**Where the extra slew violations are.** max_ss, from `area/slew_violators_h2_p2.json`: violating pins went from
281 on 50 nets to 474 on 88 nets.

| Location | h2 pins | p2 pins |
|---|---:|---:|
| inside dp | 100 | 197 |
| div↔dp | 23 | 62 |
| ctrl↔spi | 19 | 35 |
| ctrl | 46 | 64 |
| spi↔dp (score_shift) | 0 | 12 |
| ctrl↔div↔dp | 0 | 12 |

Both causes show up: weak in-cluster placement (dp) and long seams between regions.

**Verdict.** The mechanism is **proven** at full scale through signoff. The candidate is **rejected**: area +109.7,
and D2 failed.

- **Review page:** `pd_flow/review_artifacts/chip_partition_B_chip_p2.html`.
- **Spec:** `review/chip_partition_B_chip_p2.json`.

## 5. Work plan (deliverable 5)

**Order.** Freeze the netlist first, then place dp → div → ctrl → spi, then assemble. Under D7 there are no
per-module hardens. Each cluster placement is judged on the standalone dry run, `scripts/pilot_dryrun.py --through
55`: steps 17-55 with RCX and 9-corner STA, about 2 minutes. It reproduced harden p2 exactly. Hardens are only for
the final chip, for Magic DRC and LVS.

**Gate for every placement candidate** (dry run, other regions at their current placement):

- std-cell area below h2's 45,475.8;
- slew/cap/fanout within 281/2/6 at max_ss;
- setup and hold ≥ 0 at all 9 corners;
- DRT DRC 0 and antenna 0;
- resized set ⊆ reserved set, with the reservation re-probed for that exact placement.

1. **Phase 1 contracts for the remaining modules.** These are divider, mac_unit, attention_controller and top;
   ripple_add and max_reg are done, and exp_lut is in progress. Placement does not change logic, but every final
   netlist needs a gate-mode contract.
2. **Phase 2, time-boxed and measured in context only** (flat chip `ll_synth`, noise band −52.7/+234.9).
   - max_reg and exp_lut found no in-context gain. ripple_add's hybrid gains (−103/−193) are inside or near the
     band.
   - A Phase 2 change re-numbers the flat netlist. So freeze RTL and config, record the netlist sha, and only then
     place.
   - If RTL changes later, carry the placement with `remap_placement.py` (flops by Q net) and re-place the
     unmatched cells.
3. **dp cluster** (828 cells, 216 ff; the hub and the largest area).
   - **Placement:** a tetrising agent at max effort.
     - The S[21:0] bit-slices run as columns shared by mac's S register, adder 22, max S_in/M and exp D.
     - The O0 accumulator ring is a regular array.
     - L (adder 12) sits at the div edge.
     - Reuse ripple_add's tetris block and max_reg plan rev 2 as sub-placements, retargeted to the flat cells via
       the attribution.
   - **Region target:** ≤ 90% after repair.
   - **Accept** into assembly when, in the dry run, dp's inserted area (upsizing + repair + CTS share) is below
     h2's 1,233 µm², the slew violators inside dp are at most h2's 100 pins, and GRT overflow and DRT DRC are 0.
   - **The bar to beat inside dp** is GPL's wirelength on the dp nets. My annealing placer is 35% above it and
     doubles the dp slew violators (§4.5).
4. **div** (312 cells, 57 ff). A bit-sliced subtract/shift array with the O0/L inputs on the west edge and
   result[11] at the north-west corner. Accept on the same rule (h2 reserve 367 µm²).
5. **ctrl** (244 cells, 41 ff, plus the tie row). The FSM next to the mac control bundle and the flash SPI master
   under the uio pins (h2 reserve 609 µm²).
6. **spi.** Reuse `placements/spi_p1`, re-optimized against the final neighbours (anchors). Its 241 µm² of
   inserted area can only fall once exp and ctrl sit next to it.
7. **Assembly.**
   - Merge the four regions with `chip_place.py --fixed ...`. Run the probe, then the reservations, then a FIRM
     dry run through step 55.
   - Then **one** M-FIRM harden per candidate. Signoff:
     - DRC, LVS and antenna all 0;
     - slew/cap/fanout within the D2 band (≤ 281/2/6);
     - setup and hold WNS ≥ 0 at all 9 corners;
     - the post-flow validator shows 0 moved;
     - the netlist sha equals the frozen one.
   - Verification: run the frozen contracts in gate mode on the final netlist, and `eqy_rtl` with the golden RTL
     against the synthesized netlist. The resizer/CTS edits are covered by LVS and by a gate-mode run on the
     final `.pnl.v`.
   - Apply F1 (h2) to `src/` at this point, as PROGRESS.md already says.
8. **Acceptance (D3).** For a frozen netlist the flow is deterministic, so a repeat harden proves nothing.
   - Require a std-cell area below h2's 45,475.8 by more than the placement spread: 63.7 µm² measured over three
     seeds, so use ≥ 100 µm² **(estimate** of a safe margin).
   - Require the same result in two re-seeded variants of the winning placement, each with its own probe and
     reservations, all below h2 and all within D2.

## 6. Area metric against h2 (deliverable 6)

`tools/area_classes.py` reconciles exactly with metrics.json: 45,475.76 against 45,475.8. The table below is h2's
std-cell area by class.

| Class | Count | µm² | Can placement change it? |
|---|---:|---:|---|
| synthesized logic and flops (at synthesized masters) | 1,416 | 40,958.0 | no: only RTL or synthesis |
| ties | 18 | 158.1 | no |
| upsizing (final − synthesized master) | 47 cells | 781.5 | **yes** |
| repair buffers (load_slew 17, fanout 12, wire 4) | 33 | 856.1 | **yes** (the 7 fanout violations are logical and need buffers anyway) |
| CTS (clkbuf 20, clkload 11) | 31 | 851.7 | **yes** (partly: the 11 clkload dummy loads are a CTS setting) |
| hold buffers | 0 | 0 | yes (none in h2) |
| taps / endcaps | 348 / 78 | 1,527.9 / 342.5 | no: fixed by the tile |
| **std-cell total (all but fill)** | | **45,475.8** | |
| fill (free tile area) | 1,052 | 6,491.2 | |

**What can change in a fixed TT tile.**

- **Fixed:** the die (346.64 × 160.72), the core (51,967 µm²), rows, taps, endcaps and pin positions. Custom
  placement cannot shrink the die.
- **Changes:** the std-cell area metric and the free tile area (fill).
- **The ceiling:** custom placement can remove at most the 2,489.4 µm² that PnR inserts (5.5% of the std-cell
  area).
- **Measured, most of it is set by the netlist.**
  - 43 of h2's 47 upsizes (698.1 of 781.5 µm²) recur with the same master in all four placements tried: h2 GPL,
    p2, onecore_v5 and chip_v1r, with HPWL from 40.7k to 60.3k.
  - 23 of h2's 26 repaired drivers are repaired in all four runs checked (h2, p1, p2, onecore_v5). They carry
    781.5 of h2's 856.1 µm² of repair.
  - So the placement-variable part outside the clock tree is about 83 + 75 ≈ 160 µm² in h2. The clock tree
    (852, of which 96.6 is clock inverters) is variable within roughly ±45 µm² in these runs (812 to 896).
- **Realistic upside:** 0 to about 300 µm² **(estimate)**. More than that would need a different netlist or
  flow settings, such as drive strengths at synthesis, the CTS dummy loads or the repair settings, rather than
  placement.
- **Comparison:** the synthesis-side levers measured so far are the ±50 to 250 µm² noise band and F1's
  −1,343 µm².
- **Packing:** per-region packing is reported by `area_classes.py --regions` and `check_place.py --final-def`.
  - p1: 89.2% for the block, 97.5% for the region.
  - p2: spi 89.2%, ctrl 90.8%, div 90.0%, dp 86.0%; 87.6% over the whole placeable core.
  - Free tile area: 6,491.2 µm² in h2, 6,500.0 in p1, 6,381.5 in p2.

## 7. Risks

1. **Bounded upside.** See §6. The user's premise that placement always saves area holds only for the inserted
   cells. The full ceiling is 2,489 µm² in h2, but measured, only about 160 µm² outside the clock tree changes with
   placement. All four custom placements I made lost to GPL by 110 to 173 µm².
2. **Placer quality and D2 slew.** Matching GPL wirelength is the minimum. My SA reaches +6.3% unpartitioned and
   +31 to +35% with the partition.
   - The binding constraint is D2 slew, not area. Every custom placement so far raised max_ss slew violations
     (308 to 513 against 281).
   - The tetrising agents must beat GPL+DPL on the cluster nets, which a structured (bit-sliced) placement should
     do; that is not yet shown.
3. **The cost of partitioning a hub design.** mac touches every region. With the same placer, the floorplan B regions
   cost wirelength:

   | Comparison | Partitioned | Unpartitioned | Cost |
   |---|---:|---:|---:|
   | HPWL, SA v1 | 55.5k | 50.5k | +10% |
   | HPWL, SA v2 (`chip_v2` against `onecore_v4`) | 53.2k | 43.4k | +23% |
   | HPWL, SA v2 with reservations (`chip_v2r` against `onecore_v5`) | 55.0k | 43.2k | +27% |
   | Routed wirelength | 73.4k | 59.7k | +23% |

   The better optimizer makes the gap larger, not smaller, so the cost is real.

   In area, the partitioned seeds come out −50.5, +8.8 and +13.2 µm² against unpartitioned: **inconclusive**.

   In D2 slew the partition clearly costs: 474 to 513 violating pins, against 308 unpartitioned.

   Keep the mac/div and mac/ctrl seams short, treat the dp sub-regions as soft, and let the tetrising agents move the
   region boundaries (rev 2) if a seam's nets dominate their repair area.
4. **Reservation fixpoint.** One probe per placement converged in 6 of 6 cases. A reservation does not carry over
   to another placement: a re-seed changed 3 to 5 decisions out of about 50. So every candidate needs its own
   probe. A miss fails loudly with DPL-0033.

   The fallback is M-PLACED: `MANUAL_GLOBAL_PLACEMENTS` moved before RepairDesignPostGPL via
   `meta.substituting_steps` in the copy's config. It never fails, but it allows drift.
5. **Hold margin.** max_ff hold was +0.058 ns in h2, +0.047 in p1 and +0.044 in p2 (+0.081 and +0.100 for
   the re-seeds). Clustered flops change skew; watch that every corner stays ≥ 0.
6. **Netlist churn.** Any RTL or config change re-numbers instances. Only flops carry over completely; about 45% of
   the combinational cells carry structurally (measured), and the rest need re-placing.
7. **Local density in mixed custom/GPL runs.** GPL fills custom-region whitespace (the p1 region reached 97.5%).
   This does not occur in the all-custom chip, where only the 18 ties are movable.
