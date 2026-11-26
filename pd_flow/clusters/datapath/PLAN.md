# Datapath cluster tetris (mac_unit + ripple_add x2 + max_reg + exp_lut): PLAN and record

Objective (D10, `pd_flow/TETRIS_AREA_OBJECTIVE.md`, binding): minimum shipped std-cell area
(`design__instance__area__stdcell`), with packing per D8c (tighten only while dry-run area improves; stop at
convergence). Decision being executed: `pd_flow/chip_partition_DECISION.md` item 4 (seed from the tool's
placement, improve it; screen with B's dry run; harden only the winner).

Everything below is reproducible from `scripts/` (generator `gen_tetris.py` + `dpo.py` + `dplib.py`, validator
`validate.py`, screening `pipeline.py` -> `dryrun.py`, results `make_results.py`). Run dirs are under
`/Users/samuelzhang/ttharden/dp_work/<tag>_{probe<k>,firm}`; per-candidate summaries are
`placements/<tag>/firm_summary.json`; logs are `logs/<tag>.log`, `logs/gen_<tag>.log`.

## 0. References and status

| Reference | Run | Std-cell µm² | slew/cap/fanout | setup / hold min (ns) | wire µm |
|---|---|---:|---|---|---:|
| h2 (comparison netlist of the earlier work) | `/Users/samuelzhang/ttharden/fx_h2_k6/runs/wokwi` | 45,475.8 | 281/2/6 | 41.79 / 0.058 | 50,554 |
| **x0 (shipping netlist; h2 + mux2_1)** | `/Users/samuelzhang/ttharden/md_x0_full/runs/wokwi` | **44,911.6** | **242/1/0** | 43.16 / 0.0069 | 49,125 |

x0 numbers: `md_x0_full/runs/wokwi/final/metrics.json`. x0 area by class (`baseline/x0_area_classes.json`):
synth 40,646.3, upsize 805.6 (49 cells), repair 671.7 (27 buffers, 21 drivers), CTS 759.5 (23), tap 1,527.9,
endcap 342.5, tie 158.1.

**Result:** winner `xpk20_s1` signs off on x0 at **44,907.2 µm² (−4.4 vs x0)**. It has slew/cap/fanout
**189/1/0** (x0 242/1/0), setup +42.31 ns and hold +0.034 ns (x0 +0.007), and DRC, LVS and antenna 0. All
1,362 FIRM cells are held at all 16 step DEFs. The run is `/Users/samuelzhang/ttharden/dp_xpk20/runs/wokwi`.
The harden equals its dry run exactly. The gain is all timing-repair buffers (−4.39); upsizing and CTS are
unchanged. Packing converged at 86.6% (seed 83.3%). The winner and both perturbed variants pass. The recipe is
not seed-robust (§G3). Placement cfg: `macro_placement_xpk20.cfg` (= `placements/xpk20_s1/macro_placement.cfg`).

## Method steps 1-12

### Step 1. Start at the neighbours
The cluster is not a macro: it is 813 cells (x0; 828 in h2) of the flat netlist placed among the divider,
controller and SPI/config cells, which stay at their tool (x0 final DEF) positions. Its "neighbours" are the
pins of those cells and the IO pins; they are fixed points in the cost (`dplib.Wire.fixed`). Clock enters from
the clk pin (x 331.2, top right); all 216 dp flops are kept at their tool sites in the shipped candidates
(`--freeze-flops`), so the clock sink set, and with it the CTS, is the reference's (CTS area 759.5 in every
frozen-flop x0 screen, `results.json`). Growth direction: none (die fixed by the 1x1 tile; area is std-cell area).
Edge alignment to div/ctrl is the `--edge K` net weight in the generator (boundary nets; not shipped, see Step 6).

### Step 2. Expose the real graph
The graph is the reference run's synthesized netlist (`06-yosys-synthesis/*.nl.v`, x0 sha16 `99daa702b88da8c9`),
parsed by `scripts/attribute.py`. Cluster membership is structural and netlist-agnostic: flops by the public name
of their Q net (`core.mac.ring[*]`, `core.divider_unit.sum_in[*]`, `core.divider_unit.magnitude[0]` = O0 ring,
`core.exponent_unit.D[*]` = mac S register, `core.mac.M[*]` = max_reg M, `core.divider_unit.denominator[*]` =
mac L register), combinational cells by the flops their fan-out cone reaches. x0: 813 dp cells, 216 flops,
25,431.4 µm² (`baseline/x0_attribution_structural.json`). Instance names are never carried across netlists;
the x0 work re-derives everything from the x0 netlist (`DP_REF` env in `dplib.py`). The O0 ring is 160
`dffq_1` in a pure flop-to-flop shift chain (Q -> D, no logic), checked in the x0 netlist.

### Step 3. Census the routing resources
`scripts/census.py` -> `baseline/census.json` (h2) and `baseline/x0_census.json`: routing window Metal2-Metal4,
2 vertical / 1 horizontal layers (horizontal scarce), row = 7.00 Metal3 tracks (mirrored rows see the same
track set), no dp master has Metal2 shapes (Metal2 free over every cell), 30 dp masters.

### Step 4. Choose a physical grammar
Grammar terms implemented as generator options (`gen_tetris.py`), all on top of the tool seed:
- `--slices`: bit-sliced S[21:0] columns (S flop + M flop + the dp cells one net away from exactly one bit),
  columns kept in the tool's bit order, evenly spaced;
- `--ring K`: the O0 ring as an array (ring flops movable, every ring shift net weighted xK);
- `--edge K`: cluster-boundary nets to div/ctrl weighted xK;
- `--pack-w W`: compaction (sum of the cluster's per-row extents, i.e. region area / row height).
Measured verdicts (x0): slices hurt (+59.3, CTS +61.5, fanout 7: `xsl_s1`); ring as array keeps area at
+17.6 but cuts slew 242 -> 154 and wire -1,821 µm while adding CTS +8.8 (`xrg_s1`); compaction is the only
structural term that produced a gated win (`xpk20_s1`). So the shipped grammar is "tool placement + compaction".

### Step 5. Bounds
- Area floor of the cluster region: dp area 25,431 µm² plus the non-dp cells and taps inside the region.
- Pure-Tetris packing bound (`scripts/gen_packbound.py`, h2): 95.9% packing, region 30,968 µm², 231.8 µm
  wide; dry run `dp_work/pb1_firm` did **not route** (3,568 DRC violations still at detailed-route iteration
  37, run stopped; `logs/pb1_firm_drt_killed.log`). 28 reservation misses in its first probe
  (`logs/pb1.log`). It is the hostile bound the method asks for, and it confirms that ~90% is not reachable
  by moving the cluster alone.
- Seed (x0 tool placement): region 37,188.9 µm², packing 83.3% (`placements/x_s0/gen.json` footprint_seed).
- Converged (D8c): 86.6% (§ Step 10 / packing sequence).

### Step 6. Place for wires, then play Tetris
`dpo.py`: legal-move simulated annealing (relocate into free runs near the median target, same-width swaps,
mirror flips, slides), every move legal by construction (taps/endcaps, row orientation, spans). Cost (D10 §2):
item 2 by proxy = repair-weighted HPWL: nets of drivers the reference repaired or upsized x4, those with seed
HPWL >= 60 µm x30 (`--K2`), plus criticality weights from `scripts/crit.py` (`baseline/x0_crit.json`: driver
slew/cap/fanout closeness under the resizer's and the signoff wire model); item 3 = `--pack-w`; item 4 =
the weights (and optional explicit hinge targets, `scripts/targets.py`). Movable: the 813 structural dp cells
minus the 216 flops (597); every other cell keeps its tool position; reservations widen spans locally.

### Step 7. Emit one reproducible trial
One generator run writes `placement.json`, `macro_placement.cfg` (MACRO_PLACEMENT_CFG, all 1,362 non-tie
cells FIRM), `manual_global_placements.json` (probe only), `reserve.json`, `gen.json` (args, log, footprint).
x0 wrapper: `scripts/genx.sh <tag> [args]`. Validator: `scripts/validate.py <dir> --regen --movable struct`
(stale/regen byte-identity, views agree, geometry, intent = no non-cluster cell moved without a recorded
reason, netlist hash, LEF widths, self-test with a planted overlap). Winner: `logs/validate_xpk20_s1.txt`
-> `regen identical`, 1,362 cells, 18,883 site-rows, 0 non-cluster moves, self-test rejected, OK.

### Step 8. Route with placement fixed
M-FIRM (B): every non-tie cell FIRM via MACRO_PLACEMENT_CFG at step 17; the flow's own repair, CTS, resizer
and routing then run (D4: automatic routing only). Upsizing space reserved per placement by a probe of steps
17-32 (`pipeline.py`: probe -> reserve misses -> re-probe until none, at most 4 rounds; every x0 candidate
converged in <= 1 round). Screening = `dryrun.py` FIRM through step 55 (9-corner STA), the reference run's
per-step configs, at most 2 LibreLane containers machine-wide (`scripts/step_run_gated.sh`). The dry run
checks held (FIXED, same origin/orient; resized cells inside their reserved span) on every step DEF.

### Step 9. Classify the failure with data
Per candidate, `area_classes.py` splits area into synth/upsize/repair/CTS/tap/endcap/tie and lists repair
buffers and upsizes by driver; `compare.py` gives the delta per class against the reference. Findings (x0):
- FIRM itself costs +48.3 (all repair) on the x0 tool placement (`x_s0`): step 32 repairs at the final
  (legal) positions instead of the GPL positions of the reference flow. Driver-level: `_1898_` +30.7,
  `_1319_` +22.0, `_1085_` +8.8 (non-dp: unfixable by moving dp cells), `_1311_` +8.8, `_1222_` -22.0.
- Only ~7 drivers change between placements (`_1085_ _1222_ _1228_ _1311_ _1318_ _1319_ _1823_ _1898_
  _2198_`); the other 42 upsizes and ~15 repaired drivers recur in every placement. Most dp upsizes are
  pin-cap / fanout bound even at zero wire (`crit` at HPWL 0 >= 1).
- Explicit hinge targets on "removable" upsizes (`xh_s1`, `xhr_s1`) did not remove them (the aoi211 / xnor2
  upsizes are not wire driven) and caused regressions (+33.5 / +70.2, one hold violation -0.015 ns).
- Cap violations at signoff are fanout-split buffers of high-fanout nets at 0.203-0.207 pF against 0.2 pF
  (`_2208_` in every run including x0; `_1223_`, `_2007_` in `xa_s2`).
- Routing: no x0 candidate had route DRC or antenna violations; only the packing bound failed to route.

### Step 10. Relax one degree of freedom at a time
The relaxation axis here is packing (D8c), one weight at a time on the same recipe and seed. See the packing
sequence table in §G3. Other single changes tried one at a time: annealer seed, slices, ring, hinge targets.

### Step 11. Finish the route
Signoff harden of the winner only (§G2, §G2.5): `scripts/run_signoff.sh` -> `/Users/samuelzhang/ttharden/dp_<tag>`.

### Step 12. Close the repeated object
Not applicable as a tiled array: the cluster is placed in the one 1x1 tile with the chip's own taps,
endcaps, PDN and fill (the reference floorplan); there is no abutment of copies. G4 is therefore the
full-chip harden of the winner (taps, wells, power grid, IR report, antenna), §G4.

## Gates

### G0 (function)
Placement-only: the netlist is the reference's synthesized x0 netlist, unchanged (hash recorded in every
`gen.json` and checked by the validator). Function is the frozen golden's; LVS at signoff proves the
layout matches it.

### G1 (inventory, legality)
Validator OK (Step 7); probe/reservation fixpoint with 0 misses; every dry run held all 1,362 FIRM cells at
all 12 step DEFs (`firm_summary.json` `ALL_HELD`).

### G2 (fixed-placement route)
Dry run: route DRC 0, antenna 0 for every x0 candidate; signoff: §G2.5.

### G2.5 (stream-out, LVS)
Signoff harden `scripts/run_signoff.sh xpk20 placements/xpk20_s1`. It copies `md_x0_full` without runs/ and
adds one config line (MACRO_PLACEMENT_CFG); src/, tt/ and the PDK of the repo are untouched. Run dir:
`/Users/samuelzhang/ttharden/dp_xpk20/runs/wokwi` (13 min).
- **Netlist:** the synthesized netlist's sha256 equals x0's (`99daa702b88da8c9f458...`).
- **Signoff checks:** Magic DRC 0, LVS 0 (every `design__lvs_*` count 0), route DRC 0, antenna nets/pins
  0/0, illegal overlap 0, disconnected pins 9 (x0: 9). The manufacturability report passes antenna, LVS and
  DRC (`signoff/dp_xpk20_manufacturability.rpt`). KLayout DRC is not reported, the same as x0.
- **Held check:** `scripts/check_held_run.py` gives ALL_HELD over 16 step DEFs (17 to final). The 49
  in-place upsizes all sit inside their reserved spans (`logs/check_held_dp_xpk20.json`).
- **Metrics:** `signoff/dp_xpk20_metrics.json` (copy of `final/metrics.json`).

### G3 (area; D10 replaces energy)
Reference x0 44,911.6. Gate: area < ref, slew/cap/fanout ≤ 242/1/0, setup and hold ≥ 0 at all 9 corners,
route DRC and antenna 0, held, resizes within reservations.

**x0 screens** (dry run through step 55; `results.json` `x0_screens`; Δ vs x0 by class):

| tag | what | area | Δ | Δupsize | Δrepair | ΔCTS | s/c/f | hold ns | packing | gate |
|---|---|---:|---:|---:|---:|---:|---|---:|---:|---|
| x_s0 | x0 tool placement re-fed FIRM | 44,959.9 | +48.3 | 0 | +48.3 | 0 | 232/1/0 | 0.006 | 83.3% | area |
| xa_s1 | weighted anneal, seed 1 | 44,929.2 | +17.6 | 0 | +17.6 | 0 | 183/1/0 | 0.026 | 83.9% | area |
| xa_s2 | seed 2 | 44,898.4 | −13.2 | −8.8 | −4.4 | 0 | 215/**3**/0 | 0.048 | 83.9% | cap |
| xa_s3 | seed 3 | 44,929.2 | +17.6 | 0 | +17.6 | 0 | 182/1/0 | 0.007 | — | area |
| xsl_s1 | + S[21:0] bit-slice columns | 44,970.9 | +59.3 | +11.0 | −13.2 | +61.5 | 164/2/7 | 0.001 | — | area, cap, fanout |
| xrg_s1 | + O0 ring as array (ring flops movable) | 44,929.2 | +17.6 | 0 | +8.8 | +8.8 | 154/1/0 | 0.013 | 83.9% | area |
| xh_s1 | + explicit hinge targets | 44,951.1 | +39.5 | −8.8 | +48.3 | 0 | 207/2/0 | **−0.015** | — | area, cap, hold |
| xhr_s1 | + hinge + ring | 44,981.8 | +70.2 | −8.8 | +70.2 | +8.8 | 212/1/0 | 0.042 | — | area |
| xpk10_s1 | + compaction w 10 | 44,929.2 | +17.6 | −8.8 | +26.3 | 0 | 191/2/0 | 0.039 | 85.5% | area, cap |
| **xpk20_s1** | **+ compaction w 20 (winner)** | **44,907.2** | **−4.4** | 0 | **−4.4** | 0 | **189/1/0** | 0.034 | **86.6%** | **PASS** |
| xpk20_p1 | perturbed winner (13 cells, seed 11) | 44,907.2 | −4.4 | 0 | −4.4 | 0 | 189/1/0 | 0.032 | 86.6% | PASS |
| xpk20_p2 | perturbed winner (10 cells, seed 12) | 44,907.2 | −4.4 | 0 | −4.4 | 0 | 184/1/0 | 0.023 | 86.6% | PASS |

Run dirs: `/Users/samuelzhang/ttharden/dp_work/<tag>_firm` (for xsl_s1, the `_r1` reservation round).

**Where the −4.4 comes from** (signoff `logs/dp_xpk20_area_classes.json` vs `baseline/x0_area_classes.json`):

| Driver | dp? | x0 | xpk20 | Δ µm² |
|---|---|---|---|---:|
| `_1222_` (and2_1, fanout 28) | yes | 3 × buf_3 | 2 × buf_3 | −21.95 |
| `_1085_` (and2_1, fanout 14) | no | buf_3 | buf_4 | +8.78 |
| `_1311_` (and2_1, fanout 19) | yes | buf_3 | buf_4 | +8.78 |

Totals by class: repair 667.34 vs 671.73 (−4.39); upsize 805.63 vs 805.63, the same 49 cells; CTS
759.54 vs 759.54 (clkbuf_8 ×3, clkbuf_4 ×17, clkinv_4 ×2, inv_4 ×1); synth/tap/endcap/tie identical.

**Packing sequence (D8c; same recipe and seed, one weight at a time):**

| tag | pack-w | packing | region µm² | dry-run area | s/c/f |
|---|---:|---:|---:|---:|---|
| x_s0 (seed) | — | 83.3% | 37,188.9 | 44,959.9 | 232/1/0 |
| xa_s1 | 0 | 83.9% | 36,666.4 | 44,929.2 | 183/1/0 |
| xpk10_s1 | 10 | 85.5% | 35,123.2 | 44,929.2 | 191/2/0 |
| xpk20_s1 | 20 | 86.6% | 34,401.0 | **44,907.2** | 189/1/0 |
| xpk40_s1 (generated, not screened) | 40 | 86.5% | 34,449.3 | — | — |
| xpk80_s1 (generated, not screened) | 80 | 86.6% | 34,497.6 | — | — |

Density stopped rising after weight 20, so packing **converged at 86.6%** and tightening stopped (D8c). The
cause is the frozen flops: they are 216 of the 813 cluster cells and they pin each row's extremes. The
~90% figure stays a noted bound only. The pure-Tetris bound (95.9%, h2, `pb1`) did not route. The region
shrank by 2,788 µm² (−7.5%). That whitespace is not std-cell area: the die is fixed. It counts only through
the repair it changes, here −4.4.

**Robustness:** two local perturbations of the winner were re-annealed from it at low temperature with new
seeds, changing 13 and 10 cells. Both give 44,907.2 and pass every gate, so local robustness **passes**.
Recipe-level robustness was **not** shown:
- other annealer seeds of the same recipe gave +17.6 (`xa_s1`, `xa_s3`) or failed on cap (`xa_s2`);
- on h2, 1 of 17 screens passed (`v2s2`, −24.2), and the others spread from −11.0 to +72.4 (`results.json`
  `h2_screens`).

The win is small and close to the size of a single buffer decision.

**Earlier h2 work** (kept as the comparison history; netlist h2, ref 45,475.8, `results.json` `h2_screens`):
- s0r (FIRM penalty): +70.2.
- Best `v2s2`: −24.2 (209/1/6, pass).
- Partial FIRM (only the cluster fixed, other cells re-placed): `t1p`/`t7p` −11.0, but slew 302/303
  exceeds 281 and wire rises +11%.

Diagnostics (not objectives):
- **Wire:** 48,217 µm vs 49,125 (−1.8%).
- **Power, vectorless:** 2.7725 mW vs 2.7827 mW (−0.4%).

### G4 (repeated object)
No tiled copies exist, so no 2×2 abutment applies. The closing object is the full 1×1 tile, and the signoff
harden closes it:
- the reference's taps (348), endcaps (78), PDN and fill (999 fill cells);
- the IR drop report ran (step 56; `VSRC_LOC_FILES` is unset, the same as x0);
- antenna 0, and Magic DRC and LVS clean.

The cluster's placement is not yet a relocatable sub-placement (D5). It is expressed in absolute tile
coordinates against the x0 floorplan and the other clusters' tool positions.

## Risks and open items
- **Margin:** −4.4 µm² is one buffer-size decision (buf_3 vs buf_4 = 8.78). Any later change to the
  netlist or to the neighbouring clusters' placement re-rolls it. The placement does not carry over to
  another netlist: positions are keyed by instance name, so it needs a re-map by Q net and structure, then
  re-probe and re-reserve.
- **Cap is at the limit:** cap count 1 equals x0's 1. It is the `_2208_` fanout buffer at 0.205 pF against
  0.2 pF, present in every run. Two other screens tipped dp fanout buffers over the limit
  (`_1223_`, `_2007_`).
- **Hold:** x0 hold is +0.007 ns. One hinge screen broke hold (−0.015 ns). The winner has +0.034 ns.
- **FIRM penalty:** re-feeding the tool placement FIRM costs +48.3 on x0, because repair runs at
  legalized positions instead of GPL positions. The search spends most of its gain recovering this.
- **Not shipped:** slices and hinge targets lost, and the ring array lost on area while helping slew.
  Their code stays as options; their evidence is in `results.json`.
- **Containers:** the screens ran with up to 1,150 s of probe time spent waiting at the 2-container gate.
  The numbers are unaffected; the flow is deterministic.
