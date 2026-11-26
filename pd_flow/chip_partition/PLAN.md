# Chip partition, floorplan and integration plan (Architect A)

All-custom-placed TT 1x1 GF180 tile: partition, floorplan at D8 density, integration mechanism and
pilots, work order, area metric. The reference throughout is **h2 (F1)**:
- config `pd_flow/chip_flow_area/recommended_config.patch`;
- run `/Users/samuelzhang/ttharden/fx_h2_k6`;
- std-cell area 45,475.8 µm², routed wire 50,554 µm, DRC/LVS/antenna clean.

Every number below comes from a run or a script output named next to it. Estimates are labelled
**(estimate)**. Paths are relative to `pd_flow/chip_partition/` unless they are absolute.

## Result in brief

| | h2 (reference) | P1: h2 placement re-fed, all FIRM | P2: DIV packed into its region (gen2) |
|---|---:|---:|---:|
| Run | `fx_h2_k6` | `/Users/samuelzhang/ttharden/cpa_p1_refeed` | `/Users/samuelzhang/ttharden/cpa_p2_div90` |
| Custom-placed instances held exactly to final | n/a | **1,449 / 1,449** | **1,449 / 1,449** |
| Std-cell area (µm²) | 45,475.8 | 45,493.3 (+17.5) | 45,467.0 (−8.8) |
| Clock buffer + clock inverter area | 755.1 + 96.6 | 755.1 + 96.6 | 724.4 + 101.0 (−26.3 against P1) |
| Routed wire (µm) | 50,554 | 50,604 (+0.1 %) | 61,917 (+22.4 % against P1) |
| Magic DRC / LVS / antenna / route DRC | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| Max slew / cap / fanout violations (D2 band ≤ 381 / 2 / 13) | 281 / 2 / 6 | 252 / 2 / 6 | **386** / 2 / 6 (slew outside the band) |
| Setup / hold WS (ns) | 41.79 / 0.058 | 41.66 / 0.054 | 41.34 / 0.075 |

Sources:
- metrics: `analysis/pilot_metrics.json`, from `scripts/compare_runs.py`;
- held placement: `pilot/p1_refeed/held_full.json` and `pilot/p2_div90/held_full.json`, from
  `scripts/check_held.py`.

Labels:
- **P1: proven.** Every synthesized, repair and tie-driver instance stays FIXED at its configured
  site, orientation and master through every step DEF to `final`. The netlist is equivalent to the
  golden synthesis.
- **P2: failed on one signoff band (bounded).** It is clean on DRC, LVS, antenna and timing, but
  the slow-corner slew count is 5 above the D2 band.

The mechanism works. Inserting a block at a time into an existing placement does not. The plan
therefore assembles all regions in one step (§5).

## 1. Connectivity analysis (deliverable 1)

### 1.1 Synthesis boundaries: kept against flattened, h2 synthesis config

Setup:
- Driver: `scripts/ll_synth_cfg.sh`. It runs the shipped LibreLane 3.0.14 `Yosys.Synthesis` with
  `fx_h2_k6/src/config_merged.json`, so `EXTRA_EXCLUDED_CELLS` is the same in every run.
- Each run changes one override: `synth/ovr_<tag>.json`.
- Areas are recomputed from each netlist with the **full** liberty (`scripts/synth_report.py`).
  The Yosys `stat` number under h2 misses the 6 `buf_1` cells that h2 excludes from its liberty
  (41,037.07 against the true 41,116.10).

Results: `synth/synth_results.json`, `synth/synth_expvariants.json`; logs in `logs/llsynth_<tag>.txt`.

| Boundary kept | Chip area µm² | Δ against flat | Kept-scope area |
|---|---:|---:|---|
| none (flat, = h2 synthesis, sha a339bf99) | 41,116.1 | 0 | n/a |
| all hierarchy (`keep`) | 43,684.5 | **+2,568.4** | top 1,574.0, controller 5,863.4, mac 18,073.1, adder22 1,973.5, l_adder 1,062.5, max_reg 3,299.4, exp_lut 2,682.5, divider 9,156.2 |
| attention_controller | 41,252.2 | +136.1 | (core 39,678.2) |
| mac_unit | 42,134.7 | +1,018.6 | 20,843.4 |
| max_reg | 41,768.1 | +652.0 | 3,299.4 |
| exp_lut | 41,579.3 | +463.2 | 2,682.5 |
| divider | 41,974.4 | +858.3 | 9,156.2 (328 flops) |
| ripple_add ×2 | 41,792.2 | +676.1 | 1,973.5 + 1,062.5 |
| exp_lut kept, **c08** OR-merge RTL (exp_lut team) | 41,059.0 | **−57.1** | 2,114.0 |
| exp_lut kept, c10 RTL | 41,315.9 | +199.8 | 2,370.8 |

Every kept boundary costs area: +136 to +1,019 µm² for one module, +2,568 µm² for all of them.
ABC loses the cross-boundary merging; the divider keep adds 53 cells (1,487 against 1,434).

**Decision: synthesize flat and partition at the placement level.**

Response to the exp_lut data point (coordinator note):
- With its own boundary, c08 recovers the −568 µm² module-level saving: scope 2,114.0 against the
  golden 2,682.5.
- The boundary itself costs +463.2, so the net is −57.1 µm² against flat.
- That is one sample, well inside the ±130–260 µm² band that equivalent RTL texts span under this
  flow (exp_lut `OPTIMIZATION.md`).
- The boundary is not adopted on this evidence. It becomes worth a multi-text band study only if
  the cluster flow ever needs an exp_lut ABC boundary for other reasons.
- c10 behind a boundary is +199.8.

### 1.2 In-context attribution of the flat h2 netlist

Source: `scripts/attrib.py` → `analysis/h2_attribution.json`.

Method:
- Flops are grouped by Q net.
- Combinational cells are assigned by their destination/source flop groups.
- exp_lut is the cone from `exponent_unit.D` and `config_chain[7:4]` into MAC.

Totals: 41,116.1 µm².

| Module | Cells | Flops | Synth area µm² |
|---|---:|---:|---:|
| MAC (mac_unit + 2 ripple_add + ring incl. `divider_unit.sum_in`) | 615 | 194 | 20,033.4 |
| DIV (divider minus its input ring) | 318 | 57 | 8,420.8 |
| CTRL (attention_controller FSM) | 187 | 41 | 5,248.7 |
| MAX (max_reg) | 125 | 22 | 2,954.7 |
| EXP (exp_lut, combinational) | 95 | 0 | 2,438.9 |
| FE (SPI front end, config chain, synchronisers) | 40 | 15 | 1,435.7 |
| shared (MAC+MAX 153.7, DIV+MAC 61.5, CTRL+DIV 140.5, others 70.2) | 36 | 0 | 425.9 |
| ties | 18 | 0 | 158.1 |

The exp_lut team measured 2,447.6 µm² for exp_lut in context (96 cells). That agrees with the
95 cells and 2,438.9 µm² here to within one cell.

Cut bits between modules (nets crossing the boundary):

| Pair | Bits |
|---|---:|
| CTRL→MAC | 31 |
| MAC→DIV | 30 (+7 shared DIV+MAC) |
| MAC→EXP | 22 |
| MAX→MAC | 22 |
| MAC→MAX | 19 |
| shared MAC+MAX ↔ MAC/MAX | 16 each way |
| EXP→MAC | 15 |
| CTRL→FE | 11 |
| FE→CTRL | 6 |
| FE→EXP | 4 (`config_chain[7]`, fanout 19, 17 of them in EXP) |
| FE→DIV | 3 |
| CTRL→DIV | 2 |

High-fanout nets:
- clk 329 (MAC 194, DIV 57, CTRL 41, MAX 22, FE 15);
- MAX `_0492_` 44;
- MAC `_0705_` 39 and `_0704_` 31;
- DIV `_0539_` 32;
- reset gates `_1145_` (15 loads) and `_1146_` (29 loads), from rst_n & ena.

### 1.3 How h2 placed the modules

Source: the h2 final DEF, from `analysis/h2_attribution.json`. Drawing: `analysis/h2_modules.svg`.

| Module | Area (final masters) | Centroid µm | RMS spread µm | 10 µm-bin purity | Routed internal wire µm |
|---|---:|---|---:|---:|---:|
| MAC | 20,314.4 | (136, 64) | 101.9, bbox = whole core | 0.795 | 15,541 |
| DIV | 8,572.3 | (258, 86) | 103.9, strays at x = 24 | 0.756 | 9,383 |
| CTRL | 5,325.6 | (210, 119) | 44.2 | 0.741 | 2,919 |
| MAX | 2,970.1 | (109, 71) | 46.0 | 0.658 | 1,905 |
| EXP | 2,506.9 | (175, 69) | 58.3 | 0.738 | 2,738 |
| FE | 1,563.0 | (214, 123) | 72.8 | 0.646 | 757 |

Inter-module wire:
- DIV+MAC 2,392 µm (+1,037 with shared cells);
- EXP+MAC+MAX 1,143 µm;
- clock 4,775 µm.

Overlap: the MAC and DIV bounding boxes overlap 92–98 %.

What GPL does here: it interleaves the modules wherever their nets pull. It also already packs
h2 to **0.875 D8 overall** (`PL_TARGET_DENSITY_PCT` 92). Measured inside the floorplan
rectangles of §3, h2 is at 0.869–0.901.

## 2. Partition (deliverable 2)

| Block | Kind | Contents (in-context labels) | Synth area µm² | Flops | Interface | Why |
|---|---|---|---:|---:|---|---|
| **MAC-C** | coupled cluster | MAC + MAX + EXP + shared MAC+MAX, FE+MAC, DIV+MAC + repair:MAC/MAX | 25,580 (26,491.7 at h2 masters) | 216 | in: CTRL 31, FE 4; out: DIV 30+7 | Wide bidirectional buses: MAC↔MAX 22/19, MAC↔EXP 22/15, 16 shared MAC+MAX cells. Fanout 39–44 nets cross the module lines. Keeping max_reg or exp_lut apart costs +652 / +463 µm² of synthesis. |
| **DIV** | isolated | divider minus the input ring + repair:DIV | 8,420.8 (8,761.0 at h2 masters) | 57 | in: MAC 30 (+7 shared), FE 3, CTRL 2; out: 1 to FE, 1 to CTRL, uo_out[0] | One-directional input bus, few control bits. |
| **CTRL** | isolated | attention_controller, shared CTRL+*, reset gates, output port buffers, ties | 5,248.7 (5,938.0 at h2 masters incl. 18 ties and 6 port buffers) | 41 | out: MAC 31, FE 11, DIV 2; in: FE 6, flash uio_in[1,2,4,5], rst_n, ena | Control fan-out only, no wide inbound bus. |
| **FE** | isolated | SPI synchronisers, config chain, repair:FE | 1,435.7 (1,580.5 at h2 masters) | 15 | in: ui_in[0..2] SCK/MOSI/CS#; ↔ CTRL 6/11; out: EXP 4, DIV 3 | User's example of an isolated block, under its own pins. |

Synthesis boundary: **flat for all blocks** (§1.1). Each block is a placement region.

Cone membership comes from the flat netlist:
- flops map by Q net, so it survives the renumbering of `_NNNN_` instances between syntheses;
- combinational cells map by DEST/SRC flop groups.

The ports of each block are its cut nets, listed per pair and in boundary order in
`floorplan/floorplan.json` (`ports`).

## 3. Floorplan at D8 ≤ 0.90 (deliverable 3)

Source: `scripts/floorplan.py` → `floorplan/{regions.json,floorplan.json,budget.md}`. Drawing:
`floorplan/floorplan_over_h2.svg` (regions over the real h2 coordinates).

Sizing rule:
- Each region is the smallest rectangle, in whole rows and sites, with
  (cells at h2 final masters + CTS reserve + taps/endcaps inside) / area ≤ 0.90.
- The inner edge is then nudged at most 8 sites outward so it leaves no tap-segment sliver
  narrower than 4 sites.

Bands:
- band B is rows 0–31;
- band T is rows 32–38, under the pins.

| Region | rows | sites | x0–x1 µm | y0–y1 µm | area µm² | taps µm² | cells µm² | CTS reserve | D8 | free µm² |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|
| MAC-C | 0–31 | 2–443 | 4.48–252.00 | 3.92–129.36 | 31,048.9 | 873.7 | 26,491.7 | 559.2 | 0.899 | 3,124.3 |
| DIV | 0–31 | 457–604 | 259.28–342.16 | 3.92–129.36 | 10,396.5 | 289.8 | 8,761.0 | 147.6 | 0.885 | 1,198.1 |
| FE | 32–38 | 483–604 | 273.84–342.16 | 129.36–156.80 | 1,874.7 | 65.9 | 1,580.5 | 38.8 | 0.899 | 189.5 |
| CTRL | 32–38 | 29–482 | 19.60–273.84 | 129.36–156.80 | 6,976.4 | 232.7 | 5,938.0 | 106.1 | 0.900 | 699.5 |
| SPARE-B | 0–31 | 444–456 | 252.00–259.28 | 3.92–129.36 | 913.2 | 65.9 | 0 | 0 | 0.072 | 847.4 |
| SPARE-T | 32–38 | 2–28 | 4.48–19.60 | 129.36–156.80 | 414.9 | 0 | 0 | 0 | 0 | 414.9 |
| endcap columns | 0–38 | 0–1, 605–606 | | | 342.4 | 342.4 | | | | 0 |
| **core** | | | | | **51,967.0** | 1,870.3 | 42,771.3 | 851.7 | 0.875 | **6,473.6** |

Reserves, sized from h2's actual counts:
- **CTS:** 851.74 µm², which is h2's 20 `clkbuf_*` + 11 `clkload*`. It is split by flop count
  (MAC-C 216, DIV 57, CTRL 41, FE 15 of 329).
- **Repair:** h2's 33 repair buffers (856.1 µm²) are netlist members of their modules and sit in
  the cells column: MAC 351.2, DIV 171.2, FE 149.3, shared CTRL+DIV 65.9, MAX 65.9, CTRL 52.7.

Taps:
- Taps are `filltie`, 2 sites, at a 70-site period, staggered by 35 sites between even and odd rows.
  Rows 0 and 38 use a 34-site pitch.
- Endcaps occupy sites 0–1 and 605–606 of every row.
- Tap segments are 68 sites wide, and a `dffq_1` is 29 sites, so a segment holds at most two flops.
- Remaining slivers at region edges, in sites: MAC-C 11/22; DIV 13/33; CTRL and FE ≥ 5.

TT pins (top edge, Metal4, from `floorplan.json` `pins`):

| Pins | x (µm) | Region | Status |
|---|---|---|---|
| SCK/MOSI/CS# | 316.68 / 309.40 / 302.12 | FE | inside FE's x-span |
| flash inputs | 222–251 | CTRL | inside CTRL's x-span |
| six output port buffers: uo_out[0] = `divider_unit.result[11]`, uo_out[1] = `out_valid`, uio_out[0,1,3], uio_oe[1] | 76–200 | CTRL band | placed under their pins |
| rst_n, ena (drive the reset gates in CTRL) | 323.96, 338.52 | CTRL | 50–65 µm east of CTRL's span; route over FE |
| clk | 331.24 | — | goes to CTS |

Port sides (cut nets per region pair, in boundary order, in `floorplan.json`):

| Pair | Nets | Side |
|---|---:|---|
| DIV–MAC-C | 38 | DIV west side, ordered along y |
| CTRL–MAC-C | 27 | CTRL south side, ordered along x |
| CTRL–FE | 13 | CTRL east side |
| FE–MAC-C | 8 | via FE's south-west corner; EXP belongs in MAC-C's north-east |
| CTRL–DIV | 8 | CTRL's south-east corner |
| DIV–FE | 2 | DIV's north side |

Measured density in the same rectangles (`scripts/region_density.py` → `analysis/region_density.json`):

| Region | h2 | P1 | P2 |
|---|---:|---:|---:|
| MAC-C | 0.869 | 0.869 | 0.869 |
| DIV | **0.901** | 0.901 | 0.872 (DIV cells only; its CTS moved out) |
| FE | 0.854 | 0.854 | **0.916** (displaced neighbours) |
| CTRL | 0.871 | 0.867 | 0.878 |
| SPARE-B | 0.882 | 0.885 | 0.971 |

Floorplan rev A costs wire. The whole-chip generator (`scripts/chip_place.py`, gen3) gives these
pre-route HPWL figures (`pilot/p3_chip/*/relocate_report.json`):

| Placement | HPWL µm | Δ against h2 |
|---|---:|---:|
| h2 | 43,267 | — |
| gen3 with no regions (generator quality alone) | 50,747 | +17.3 % |
| gen3 in these regions | 57,807 | +33.6 % |

So segregation into rev A costs about +7,060 µm of HPWL (estimate, pre-route). The largest items:
- CTRL internal +1,738, because the band is 254 × 27 µm;
- CTRL/FE↔MAC-C +3,300;
- DIV↔MAC-C +1,267.

DIV internal wire drops by 1,563.

**Rev B:** follow h2's organisation, with CTRL a near-square block in the upper middle over an
L-shaped MAC-C, and keep FE and DIV where they are. It is the next floorplan action.

## 4. Integration mechanism (deliverable 4)

LibreLane 3.0.14 can be fed a full placement. Flow-built CTS, ties and repair cells still get
legal sites.

### 4.1 Generator side

`scripts/make_pilot.py` builds `pilot.v`, `placement.cfg` and `manifest.json` from any
signed-off or generated netlist and placement:
- **Removes** physical-only cells (fill, fillcap, filltie, endcap); the flow re-inserts taps and
  endcaps at identical, deterministic sites.
- **Removes** the clock tree (`clkbuf_*`, `clkload*`), then reconnects every pin on a clock-tree net
  to `clk`.
- **Folds** `assign port = net;` into the driver pin. The 18 tie-driven ports need this because
  `Checker.NetlistAssignStatements` rejects assigns and `SYNTH_ELABORATE_ONLY` keeps every wire.
- **Keeps** every other instance at its master: repair buffers, upsized cells and ties.
- **Applies `--presize`**, swapping in the masters that the resizer would pick. Pins are asserted
  identical across drive strengths.
- **Applies `--relocate`**, taking positions from a generator.
- **Checks G1 legality** on the site grid with the chip's taps and endcaps: on-site, in-core, row
  orientation, no overlap. A clashing cell moves by order-preserving in-row sliding
  (`scripts/placelib.py`).

### 4.2 Flow side

`scripts/run_cp.sh` makes a space-free copy of the h2 setup and changes only:
- `VERILOG_FILES = [pilot.v]`;
- `SYNTH_ELABORATE_ONLY = true`, so there is no re-synthesis and names are kept;
- `MACRO_PLACEMENT_CFG = placement.cfg`, so `Odb.ManualMacroPlacement` marks every instance FIRM.

Global placement then logs "All instances are FIXED/FIRM … Skipping" (step 28). The rest of the
flow is untouched:
- `RepairDesignPostGPL` still runs `repair_design` and `repair_tie_fanout`;
- CTS inserts `clkbuf`/`clkload` cells, which DPL legalizes into free sites;
- `ResizerTimingPostCTS` handles setup and hold (no hold buffers were needed);
- routing, fill and signoff as in h2.

### 4.3 Hazards and how they are handled

1. **Resizer upsizes a FIRM cell in place, then DPL-0033.**
   - Observed in P1 attempt 2: `_1248_` oai31_1 → oai31_2 overlapped a tap and `_1568_`. Log:
     `pilot/p1_refeed/attempt2_dpl0033_FAILED/`.
   - Fix: a fixed-point loop. Run a partial to step 32, pre-size what the resizer chose, slide the
     neighbours, and repeat. P1 converged in 1 iteration (+17.5 µm²). P2's repair step then found
     0 resizes and 0 buffers.
   - The alternative (`RUN_POST_GPL_DESIGN_REPAIR=false`) is not needed, and it would hand slew
     repair back to signoff luck.
2. **Assign statements.** Folded, as above. The failed run is kept in
   `pilot/p1_refeed/attempt1_assign_FAILED/`.
3. **Ties are re-created.** `repair_tie_fanout` deletes the 18 ties and re-inserts them next to
   their loads, so they are not held. The count and area are unchanged (158.1).
4. **Flop renumbering.** With ELABORATE_ONLY the names are those of the fed netlist. Generators that
   start from a new synthesis map cells by Q net and cone (`attrib.py`), never by `_NNNN_` name.
5. **CTS needs contiguous gaps.**
   - In P2 the DIV region's whitespace was spread evenly in sub-cell gaps. Its clock buffers landed
     outside the region: CTS inside DIV fell from 220 to 18 µm², and the FE region went to 0.916.
   - Generators must reserve explicit clock-buffer sites next to flop groups, not a percentage.
6. **`dont_touch`.** Setting it on loads triggers RSZ-3006. Do not use it; FIRM plus the presize
   loop is enough.

### 4.4 Verification per run

- `scripts/check_held.py` reads every step DEF from step 17 to `final`. It requires all non-tie
  instances FIXED at the exact coordinates, orientation and master, and it classifies every added
  instance.
  - P1: 1,449/1,449 held at every step. Added: 426 taps/endcaps, 31 CTS, 17 re-created ties,
    fill (`pilot/p1_refeed/held_full.json`).
  - P2: the same, with 30 CTS (`pilot/p2_div90/held_full.json`).
- **Equivalence:** Yosys `equiv_make`, `equiv_simple -seq 2` and `equiv_induct` against the golden
  flat synthesis (`gold_synth.nl.v`, sha a339bf99). 5,533/5,533 `$equiv` cells are proven on the
  final `pilot.v`: assigns folded, `_1248_` pre-sized (`pilot/p1_refeed/equiv/equiv_final.log`).
  The P2 netlist body is byte-identical to P1's; only the header differs.
- In-flow LVS 0, Magic DRC 0, antenna 0.

### 4.5 Pilots (2 full hardens used, one at a time, after checking `docker ps`)

**P1 `p1_refeed`: the h2 final placement re-fed with all 1,467 instances FIRM.** Proven lossless
apart from the presize:
- area +17.5 µm², which is the presize;
- wire +0.1 %;
- same CTS: 22 clock buffers + 9 clock inverters;
- signoff clean.

**P2 `p2_div90`: the DIV cluster packed into its floorplan region.** Rows 0–31, sites 457–604;
325 cells; 0.871 D8 before CTS.

Generators:
- **gen1, affine map: rejected**, pre-route HPWL +42 % (`pilot/p2_div90/gen1_affine_REJECTED/`).
- **gen2: used.** Analytic quadratic, recursive bisection, tap-segment first-fit-decreasing,
  same-width swaps (`scripts/region_place.py`).
  - 116 neighbour cells had to leave the rectangle: Σ 11,578 µm, max 362 µm. Another 161 were slid.
  - Pre-route HPWL +20.9 %.
  - Routed: clean, timing met, wire +22.4 %.
  - DIV's clock tree shrank by one `clkbuf` (−26.3 µm²).
  - Slow-corner slew rose to 386 (max_ss; nom_ss 288), outside the D2 band. Result: **failed on
    one band**.

## 5. Work order (deliverable 5)

Order of work, with the reason:
1. **Floorplan rev B and the generator contract.** Settle regions before any cluster work. Use
   CTS-gap reservation (hazard 5). Freeze the I/O contract per cluster: its cut nets by Q net, and
   the port side and order from `floorplan.json`.
2. **FE.** Smallest, under its pins. It proves the loop end to end on a block.
3. **CTRL.** Control logic. The aspect ratio needs rev B.
4. **DIV.** The gen2 region placement already exists. It needs the CTS gaps and its 38-net west port
   ordered against MAC-C.
5. **MAC-C.** The largest cluster. Reuse:
   - the ripple_add carry columns (`modules/ripple_add/REPORT.md`) inside it, not as islands;
   - max_reg layout plan rev 2;
   - exp_lut in context (golden; c08 only if a boundary is ever adopted, §1.1).
6. **Whole-chip assembly and signoff.** One step; see the closing paragraph of this section.

Per cluster (steps 2–5):
- **Phase 1, verification of the slice.**
  - The cluster's cone and ports are extracted from the flat synthesized netlist: frozen contract,
    gate mode, flops by Q net.
  - If the RTL is restructured: `eqy_rtl` against the golden RTL, plus a whole-chip Yosys `equiv`
    in gate mode.
  - If not, only the cone and contract check.
- **Phase 2, placement.**
  - Datapaths (MAC ring, adders, max_reg compare and mux, divider subtract and shift): a
    structured tetris generator (bit slices in rows).
  - Control (CTRL, FE, DIV FSM): analytic generator (gen2), later seeded from a GPL run fenced to
    the region.
  - Every generator outputs a `--relocate` map.
- **Verification gates, in order.**
  1. G1 legality (`make_pilot.py` asserts).
  2. Cluster HPWL ≤ the cluster's h2 HPWL (`scripts/hpwl.py`, by cluster set).
  3. Partial run to step 43 with presize iteration until step 32 shows 0 resizes.
  4. `check_held.py` ALL_HELD.
  5. GRT overflow 0 and usage ≤ h2 + 3 points.

  No full harden is spent until every cluster passes these gates.

**Whole-chip assembly:**
- All regions are placed together in one generated netlist and placement. Block-at-a-time
  insertion displaces neighbours (P2).
- The netlist starts from the flat synthesis with h2's repair and upsizing **stripped**, so the
  flow re-adds only what the custom placement needs. This is the experiment that measures the
  area gain.
- Then: presize loop, partial runs, one full harden, and signoff (DRC/LVS/antenna, D2 slew/cap/fanout
  band, timing, `check_held`, Yosys equiv). Compare area by class against h2.

## 6. Area metric against h2 (deliverable 6)

What can and cannot change in a fixed 1x1 tile:
- **Fixed by the tile:** die 346.64 × 160.72 µm and core 51,967.0 µm²; taps and endcaps 1,870.3 µm²
  (deterministic); ties 158.1 (18, one per constant output, re-created by the flow). 1x1 is the
  smallest TT tile, so saved area cannot shrink the die. It becomes free area (fill, 6,491.2 in h2).
- **Fixed by synthesis, not placement:** synthesized logic 41,116.1 (flat), including 329 flops.
  This changes only through RTL or synthesis (§1.1).
- **Placement-addressable:** repair buffers 856.1 (33), clock tree 851.7 (31), upsizing about
  781.6. That is a total of **about 2,489 µm² (estimate**; upsizing is the residual
  45,475.8 − 41,116.1 − 1,870.3 − 856.1 − 851.7). Repair and upsizing are frozen in P1/P2
  because the fed netlist is h2's. Only the assembly with them stripped can show them drop.

| Class (µm²) | h2 | P1 | P2 |
|---|---:|---:|---:|
| sequential | 20,986.1 | 20,986.1 | 20,986.1 |
| multi-input combinational | 19,857.8 | 19,875.3 | 19,875.3 |
| inverter | 763.9 | 763.9 | 763.9 |
| buffer + timing-repair buffer (the 33 repair buffers are classed "buffer" once they are fed in) | 131.7 + 856.1 | 987.8 + 0 | 987.8 + 0 |
| clock buffer + clock inverter | 755.1 + 96.6 | 755.1 + 96.6 | 724.4 + 101.0 |
| tie | 158.1 | 158.1 | 158.1 |
| tap + endcap | 1,870.3 | 1,870.3 | 1,870.3 |
| **std-cell total** | **45,475.8** | **45,493.3** | **45,467.0** |
| free area (fill) | 6,491.2 | 6,473.6 | 6,500.0 |

Packing:
- **Per region:** see §3 (measured: h2 0.854–0.901, P2 DIV 0.872).
- **Whole chip:** 0.875 D8 for h2, P1 and P2. At D8 ≤ 0.90 per region, the tile keeps 6,473.6 µm²
  free. Of that, 1,262.3 is in the spare regions; the rest is the ≤ 10 % whitespace inside regions.

Gains measured so far:
- clock −26.3 µm² from compacting DIV's 57 flops (P2, one sample);
- nothing from density, because h2 is already at D8 0.875–0.90.

The realistic ceiling for custom placement in this tile is the addressable ~2,489 µm²
**(estimate)**, minus whatever the clock tree and repair irreducibly need.

## 7. Risks

1. **Generator quality.** A simple analytic generator is +17 % HPWL against GPL with no regions.
   Custom placement only wins where structure lets a tetris beat GPL (datapaths), or where it is
   seeded from GPL. Otherwise wire, slew and repair grow (P2).
2. **Segregation cost.** Hard regions cost +16 % HPWL in rev A (gen3, estimate). Interleaved pairs
   are the worst: MAC↔DIV with 92–98 % bbox overlap in h2, and CTRL↔MAC. Rev B and ordered port
   cells at the boundaries are needed.
3. **Single-block insertion displaces neighbours.** P2: 116 cells, +22 % wire, slew out of band.
   Never insert blocks one at a time; assemble all at once.
4. **No density headroom.** h2 is at D8 0.875 overall and 0.90 in DIV's rectangle. "Compaction to
   90 %" gains nothing by itself.
5. **CTS sites.** Evenly spread whitespace pushes clock buffers out of dense regions (P2).
6. **Presize loop.** It may need several iterations once repair and upsizing are stripped. Each one
   is a partial run (~1 min) and needs the shared Docker slot.
7. **Synthesis noise.** Equivalent texts span ±130–260 µm². Boundary and RTL choices worth less than
   that need multi-sample bands.
8. **Ties are not held.** Harmless for area, but any tie-position assumption breaks.

## 8. Files

Scripts, all in `scripts/`:
- `ll_synth_cfg.sh`, `run_synth_batch.sh`, `synth_report.py`: synthesis boundary runs;
- `pdlib.py`: parsers;
- `attrib.py`: in-context attribution and h2 placement statistics;
- `svg_modules.py`: drawings;
- `floorplan.py`: regions, budget, pins, ports;
- `placelib.py`: site grid, segments, sliding legaliser;
- `make_pilot.py`: netlist and placement feeding;
- `run_cp.sh`: pilot harden and partial runs;
- `check_held.py`: placement held per step;
- `region_pack.py` (gen1, rejected), `region_place.py` (gen2), `chip_place.py` (gen3): generators;
- `hpwl.py`: pre-route HPWL by cluster;
- `region_density.py`: measured D8 per region;
- `compare_runs.py`: signoff and area classes.

Data:
- `synth/`, `analysis/`, `floorplan/`;
- `pilot/p1_refeed/`, including failed attempts 1 and 2 and `equiv/`;
- `pilot/p2_div90/`, including gen1 rejected;
- `pilot/p3_chip/`, gen3 estimates;
- `logs/`.

Runs:
- `/Users/samuelzhang/ttharden/cpa_p1_refeed`;
- `/Users/samuelzhang/ttharden/cpa_p2_div90`;
- `/Users/samuelzhang/ttharden/cpa_llsynth/<tag>`.

Review artifact: `pd_flow/review_artifacts/chip_partition_A_p2_div90.html`.
