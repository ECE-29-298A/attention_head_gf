# max_reg: Phase 3 layout plan (Agent 4, layout architect)

Date: 2026-11-26. Scope (D4/D5): placement of existing GF180 7-track cells only, automatic routing,
a relative sub-placement that composes into the whole-chip tetris. Nothing in `src/`, the reference
project or the PDK was edited. Nothing was committed. Every number comes from a run in this
directory, with its source named; estimates are marked **(estimate)**. Tables with every metric are
generated from the raw outputs into `tables.md` (`tools/make_tables.py`).

## 0. Verdict

1. **Shipped chip: keep (c), free placement of the golden RTL.** Both constrained options were measured
   on the chip with full hardens, and each one is worse than the baseline, mostly outside the noise band:

   | Run (full harden) | Std-cell µm² | ss WNS ns | Slew/Cap/Fanout | Power mW | Routed wire µm |
   |---|---:|---:|---|---:|---:|
   | **baseline (c) free** | 46,819.2 | 41.79 | 381/1/11 | 3.050 | 53,890 |
   | noise band (golden rewrites base, n03, n04) | 46,819–47,221 | 38.21–42.90 | 260–381 / 1–2 / 11–13 | 2.971–3.220 | 51,958–53,890 |
   | (b) `b_m`: 22 M flops fixed in one column | 46,784.1 (−35) | 39.14 | 365/**4**/12 | 3.064 | **56,605** |
   | (b) `b_ms`: M flops + mac S flops fixed, bit-aligned pair | 46,909.2 (+90) | **36.14** | **388/3**/11 | 3.129 | **62,682** |
   | (a) `a_sdff`: whole bit-sliced block fixed | **48,151.7 (+1,332)** | **34.44** | **418**/2/11 | **3.545** | **66,123** |

   Bold = outside the band. Sources: `chip_runs/{b_m,b_ms,a_sdff}/harden/metrics.json`,
   `../../../baseline/harden/metrics.json`, `../../ripple_add/layout_plan/chip_runs/{n03,n04}/harden/metrics.json`.
   All runs: 0 setup/hold violations, route DRC 0, Magic DRC 0, LVS 0, antenna 0.
2. **(b) placement-only is the right shape, but this context has nothing to gain from it.** The
   `b_*` runs synthesize a netlist byte-identical to the baseline's (`cmp` of the step-6 netlists),
   so every delta is placement alone. The free placer already arranges the 22 M and 22 S flops as a
   ring around their shared logic (mean M–S distance 17.9 µm, `ctx/base_ctx.json`). A straight column
   raises max_reg wire by +0.9 to +3.8 mm and rest-of-chip wire by +1.9 to +5.0 mm (`chip_runs/netlen.log`).
   It also moves the ss critical path to mac_unit's adder → S[21] (§2.4).
3. **(a) the fixed block loses on every axis.**
   - Synthesis: +548.8 µm² in context (`chip_runs/synth_stat/statdiff_blocks.txt`), outside the synthesis
     band (−52.7 / +234.9). The block's own cells (2,952.5 µm²) equal ABC's in-context max_reg (2,954.7 µm²,
     Phase 2 `cone.py`). ABC's rest-of-chip mapping grows by ~550 µm² **(estimate:** chip delta minus block
     delta). That is the same context loss ripple_add measured.
   - Harden: +1,332 µm², with +439 µm² of repair buffers.
   - Rest-of-chip wire +11.1 mm: a 39 × 90 µm FIXED block in a 90%-utilized die displaces its neighbours.
   - Power +16%, mostly combinational (internal 0.46 → 0.58 mW, switching 0.51 → 0.69 mW, nom_tt `power.rpt`).
4. **Integration findings (measured, new since ripple_add):**
   - `MACRO_PLACEMENT_CFG` keeps location and status but **not the master**: RepairDesignPostGPL resized
     FIXED `aoi222_1` cells in place (log: 28 to `aoi222_4`, 2 to `aoi222_2`). Detailed placement then failed on 30 overlaps
     (`chip_runs/a_sdff_aoi222_FAILED/harden_failed/openroad-repairdesignpostgpl.log`). Cause: `aoi222_1` has
     an ss rise transition of about 3.5 ns, above `MAX_TRANSITION_CONSTRAINT` 3 ns. A fixed block may
     contain only cells that repair has no reason to touch; the validator now enforces this (slew rule).
   - With slew-legal cells the block held: 109/109 FIXED at their exact coordinates, masters unchanged,
     in every step DEF (`chip_runs/a_sdff/placement_check.json`). b_m held 22/22 and b_ms 44/44, with the Q nets intact.
   - `sdffq_1` is in the PDK's `no_synth.cells`, so Yosys reports its area as unknown and under-reports
     the chip area by 1,835 µm². `tools/statdiff.py` adds it back from the Liberty. `mux2_1` is in
     `drc_exclude.cells`, so a hand netlist must use `mux2_2`.
5. **Tetris track for max_reg:** max_reg must not be a frozen block or a stand-alone register column.
   Its registers are only worth placing jointly with mac_unit's S register and adder bit-slice, which drive the
   new critical path. The deliverables below (netlist, generator, validator, sub-placements, stable-name
   mechanism) are the inputs for that joint step and for Phase 4 evidence.

**Budget:** 4 full harden launches, one at a time, mirrors `/Users/samuelzhang/ttharden/mr3_<tag>`:
- `b_m`, 69 s;
- `a_sdff` with aoi222, failed at step 32 after 19 s, counted against the budget;
- `a_sdff`, 77 s;
- `b_ms`, 74 s.

(`chip_runs/logs/harden_*.txt`.)

## 1. Method and evidence

| What | How | Evidence |
|---|---|---|
| Library | LEF census (`tools/lefcensus.py`, reused from ripple_add): site 0.56 × 3.92, M1/M3 horizontal, M2/M4 vertical, pitch 0.56; pin access per master; Liberty arcs and transitions per pin (`tools/arcs.py`) | `census.json` (LEF sha256 `47dadf84…`), `evidence/lefcensus.log`, `evidence/arcs_ss_summary.txt` |
| Chip context | Baseline DEF: 39 rows × 607 sites; FIXED fillties every 70 sites, at site 0 mod 70 in odd rows and 35 mod 70 in even rows; rows 0 and 38 dense; endcaps at sites 0 and 605 (asserted in `gen_placement.chip_context`). 33-site windows free in every row: [37, 70) and [72, 105) mod 70 | `gen_placement.py`, `validation_run.log` |
| Where max_reg sits today | `tools/ctxmap.py` on the final DEF and pnl: M flops, S flops, max_reg exclusive cone (the `cone.py` definition), consumers of M | `ctx/*_ctx.json` |
| Flop names | `tools/flopnames.py` over 26 shipped-flow netlists | `names/flopnames_all.json`, `names/stability.json` |
| Synthesis | `pd_flow/scripts/ll_synth.sh` (cell netlist as `max_reg.v`), `tools/statdiff.py` | `chip_runs/logs/llsynth_*.txt`, `chip_runs/synth_stat/` |
| Harden | `tools/harden.sh` (from ripple_add): mirror without `runs/`, 7 RTL files, overlay merged into the mirror's `src/config.json`, `tt_tool.py --harden`. Step DEFs of ManualMacroPlacement, GPL, DPL and CTS are kept | `chip_runs/<tag>/harden/` (metrics, resolved config, DEF/nl/pnl, 9-corner STA reports, SHA256SUMS) |
| Placement held? | `tools/check_placed.py`: every cfg line in each step DEF, with status, master, exact xy and orientation, plus the Q net in the final pnl | `chip_runs/<tag>/placement_check.json` |
| Wire attribution | `tools/netlen.py`: routed DEF segments summed per class (max_reg / clock / rest) | `chip_runs/netlen.{log,json}` |

## 2. Options and chip-level judgement

### 2.1 (a) Fixed bit-sliced block, `a_sdff`
- **Row grammar (bit i in relative row i):**
  - one `sdffq_1`: flop and load mux in one cell, Q+ = SE ? SI : D, with D = S_in[i], SI = M[i] and
    SE = nld (hold when 1);
  - compare stage i: `inv_1`, `nand2_1`, `nor2_1` and the chain cell, an `aoi21_1` or `oai21_1` in
    alternating polarity, so every chain cell is one 2-stack gate. Full equations are in
    `gen_placement.build_block`;
  - bit 0 has no stage (c[1] = S_in[0], the Phase 2 tie don't-care), and bit 21 compares in offset binary;
  - decode row 22: `inv_1` (gt), `oai21_1` (nld = ~(en & (first | gt))), and a `buf_4` driving the 22 SE pins.
- **Why `sdffq_1`:** its 83.4 µm² replaces `dffq_1` + `mux2_2` at 96.6 µm². A literal flop + mux + compare
  row is 29 + 15 + 23 = 67 sites, which cannot fit one 70-site tap period with the compare stage on the
  correct side. Yosys never infers `sdffq_1` (no_synth), so a cell netlist is the only way to use it.
- **First version, rejected:**
  - per-stage `aoi222_1` majority, 30.7 µm² per stage, 2,722 µm² block;
  - the harden failed (§0.4);
  - the dffq + mux2_2 version of it was 3,011.8 µm², synth +608 (`superseded/`, its contract 19/19).
- **Shipped-flow synthesis:** 41,664.9 µm² (+548.8). The cell-family diff outside the block is identical
  for all three frozen variants (`statdiff_blocks.txt`), so it is a deterministic consequence of freezing
  the boundary, not ABC run-to-run chaos.
- **Harden:** see §0. The repair-buffer class rose by 439 µm². The ss critical path is
  `config_chain[7]` → mac adder → S[21] (§2.4).

### 2.2 (b) Placement-only, ABC's in-context logic free
- `b_m`: the 22 shipped-flow M flops (`dffq_1`) in one 29-site column inside a 33-site tap window, at
  anchor row 6, site 177 (x 102.48, y 27.44–109.76). Bit 0 is at the bottom and Q faces east.
- `b_ms`: S flop i (mac_unit S register, Q net `core.exponent_unit.D[i]`) at rel site 0 and M flop i
  at rel site 35, in the same row, from anchor row 6, site 142. The tap column falls between them.
- The anchor, bit order and mirror were chosen by an HPWL proxy over all legal anchors, with free
  neighbours at their baseline positions **(estimate)**:
  - `b_m`: column 2,213 µm against 951 µm for the free baseline positions;
  - `b_ms`: 5,056 against 2,820.

  The proxy already predicted that a column cannot beat the free ring. The hardens confirmed it.
- **Results:**
  - **`b_m`:**
    - inside the band: area, WNS, slew and power;
    - outside the band: cap 4 (on non-max_reg nets: `_2344_` divider, fanout buffers, `checks.rpt`)
      and wire +5%.
  - **`b_ms`:** WNS −5.66 ns, cap 3 and wire +16%, all outside the band.
  - **Mean M–S distance:**
    - baseline 17.9 µm;
    - `b_m` 43.5 µm, because the free S flops did not follow the column;
    - `b_ms` 19.6 µm by construction. Its S Q-net HPWL still rose from 1,576 to 2,574 µm, because S also
      feeds the mac adder and exp_lut (`ctx/`).

### 2.3 (c) Free placement (baseline)
The shipped result, unchanged. The flow is deterministic: the `b_*` synthesis netlists are byte-identical
to `ll_synth base`, and the flop names and baseline numbers reproduce.

### 2.4 Attribution (why the constrained runs lose)
- **Wire** (`chip_runs/netlen.log`):

  | Run | max_reg nets | rest of chip | clock |
  |---|---:|---:|---:|
  | `b_m` | +891 µm | +1,895 µm | −75 µm |
  | `b_ms` | +3,790 µm | +5,039 µm | |
  | `a_sdff` | +960 µm | **+11,058 µm** | +213 µm |

  Fixed objects in a 90%-utilized die push the rest of the placement around. As in ripple_add, the
  isolated block is a diagnostic.
- **Timing:** the ss worst path moved from the divider (`divider_unit.state[0]` → `result[11]`,
  baseline) to `config_chain[7]` → mac_unit's 22-bit ripple adder → S[21] (`core.exponent_unit.D[21]`)
  in all three constrained runs (`chip_runs/<tag>/harden/sta_postpnr/max_ss_125C_3v00/max.rpt.gz`).
  Fixing M or S lengthens the adder's path to S, because S is the adder's register. Any S or M alignment
  belongs to the mac_unit bit-slice.
- **Power** (nom_tt `power.rpt`, vectorless): seq / comb / clock in mW.

  | Run | seq | comb | clock |
  |---|---:|---:|---:|
  | base | 1.114 | 0.967 | 0.389 |
  | `b_m` | 1.124 | 0.970 | 0.386 |
  | `b_ms` | 1.136 | 0.991 | 0.398 |
  | `a_sdff` | 1.172 | 1.268 | 0.404 |

  The block's loss is combinational: a 21-stage chain that toggles with S every SCORE clock, plus the extra
  wire. Activity is vectorless, not a workload.

## 3. Flop instance names (option b)

### 3.1 Stability (`names/stability.json`)
- Yosys names the 22 M flops `_NNNN_` in netlist order, for example `_2277_` to `_2298_` in the baseline.
  The 22 S flops sit just before them (`_2255_` to `_2276_`).
- **The names are deterministic for identical input:**
  - baseline nl and pnl, `ll_synth base`, and the `b_m`/`b_ms` harden synthesis all give the same names;
  - cosmetic edits that leave the cell count before them unchanged also keep the names (n01, n02,
    n04, g_v1, g_v3, g_v6, g_v7, g_v8).
- **They are not stable under perturbation:** 11 of 26 netlists differ (n03, n05, n06, g_v2, g_v4,
  g_v5, c01, c10, and the three ripple_add hardens).
- In every netlist the blocks stay contiguous and in bit order. The Q nets (`core.mac.M[k]`,
  `core.exponent_unit.D[k]`) are public wire names and never change.

### 3.2 How to fix only them (used in `b_m`, `b_ms`)
1. Generate the cfg from the run's own synthesized netlist (`gen_placement.py --names-netlist`,
   `out/b_*/names.json`): map Q net to instance, then write `MACRO_PLACEMENT_CFG` lines with the instance names.
2. The flow is deterministic, so the harden re-synthesizes exactly those names. This was verified: the harden's
   step-6 netlist equals the netlist the names came from.
3. After the run, `tools/check_placed.py` asserts per instance: FIXED, exact coordinates, master unchanged,
   and the Q net still on the intended bit. Results: `b_m` 22/22, `b_ms` 44/44, in the step-17, DPL, CTS and
   final DEFs.

### 3.3 Stable-name alternative (measured, not adopted)
- `out/max_reg_b_flopcells.v` instantiates the 22 flops as `dffq_1 bNN_ff` and keeps the golden next-state
  expression behavioural, so ABC still maps the compare and load mux in context. The chip names become
  `core.max_unit.bNN_ff`, independent of numbering.
- Contract (gate mode) 19/19, `eqy_rtl` proven (`contract_b_flopcells/`).
- Shipped-flow synthesis 41,048.0 µm² (−68.1, at the lower edge of the synthesis band).
- Use it if whole-chip tetris needs names that survive edits elsewhere. It would need the same
  `ifdef` guard as §4. S flops would need the same treatment in mac_unit.

## 4. Netlist (deliverable 2)

| File | Content | Contract (`verif/run_all.sh`, hash `6d7f5b5ff9a94fc9`, 16/16 files OK) |
|---|---|---|
| `out/max_reg_a_sdff.v` | 109 cells: 22 `sdffq_1`, 21 × (`inv_1`, `nand2_1`, `nor2_1`), 11 `aoi21_1` + 10 `oai21_1` chain, decode (`inv_1`, `oai21_1`, `buf_4`). 2,952.5 µm² | `--gate`: **19/19**, all proven/pass: k-induction and abc pdr (step, seq, power-up), 23/23 covers, vectors 4-state Icarus, `eqy_rtl` proven, both sanity controls fail as required (`contract_a_sdff/results.json`, `contract_a_sdff.runlog`) |
| `out/max_reg_chip.v` | golden module under `` `else ``, the a_sdff body under `` `ifdef MAX_REG_CELLS `` (set only through `VERILOG_DEFINES`) | RTL mode, define off: **17/17** (`contract_chip_rtl/`) |
| `out/max_reg_b_flopcells.v` | §3.3 | `--gate`: **19/19** (`contract_b_flopcells/`) |
| `superseded/max_reg_a_{sdff,dff}_aoi222.v` | rejected first version | `--gate` 19/19 each (`superseded/contract_*`) |

The validator independently evaluates the next state of the netlist cell by cell from Liberty functions
(flops from the Liberty `ff` next_state). It runs 262,208 vectors with 25% near-ties and 5% exact ties,
and gets 0 mismatches against the golden signed rule (`validation_run.log`).

## 5. Coordinate-level placement (deliverable 3)

### 5.1 `a_sdff` sub-placement (`out/a_sdff/placement.{csv,json,svg}`, `chip_anchor.cfg`)
- **Footprint:** 70 sites × 23 rows = 39.20 × 90.16 µm (3,534.3 µm² box).
  - Cells use 1,345 of 1,610 site-rows (**83.5%**). 46 site-rows are the chip's own taps inside the
    footprint (rel site 18 in even rows, 53 in odd rows); without them, utilization is 86.0%.
  - The widest row is 61 sites. The free sites are ragged capacity for neighbours (D5), not a halo.
- **Bound:** a row cannot be narrower than sdffq (38 sites) plus the compare stage (23), all inside one
  tap period. 70 sites is one period, so the footprint sits at the bound for one bit per row. Two bits
  per row would need 122 sites, about two periods: no gain.
- **Row templates** (anchor site ≡ 17 mod 70, anchor row even):

  | Row | West → east (rel sites) |
  |---|---|
  | even | inv 0, nand2 4, nor2 9, (tap 18), oai21 chain 20, sdffq 28 |
  | odd | aoi21 chain 7, sdffq 15, (tap 53), inv 55, nand2 59, nor2 64 |
  | decode | inv 0, oai21 4, (tap 18), buf_4 20 |

  - The chain cells sit at rel sites 20 and 7: every hop is 13 sites plus one row (7.3 µm + 3.92 µm).
  - In odd rows the p/t gates sit east of the tap, about 25 µm from the chain cell. That is the cost of a
    38-site flop on a 70-site tap grid.
- **Orientation:** row-native N in even rows and FS in odd rows. Every master has `SYMMETRY X Y`.
- **Pin access** (on-grid Via1 points 0.28 µm or more inside the outline, `census.json`, validator check 8):

  | Master | Access points per pin |
  |---|---|
  | sdffq_1 | D 3, SE 1, SI 1, CLK 2, Q 1 |
  | aoi21_1 | 2 / 2 / 2 / 2 |
  | oai21_1 | A1 1, A2 1, B 3, ZN 2 |
  | nand2_1 | 1 / 1 / 1 |
  | nor2_1 | 2 / 1 / 3 |
  | inv_1 | 1 / 1 |
  | buf_4 | I 3, Z 4 |

  No pin can be blocked by an abutting neighbour.
- **Power and taps:**
  - VDD and VSS are Metal1 abutment rails, and no cell has Metal2 or higher shapes.
  - The chip's FIXED fillties fall inside the footprint at the template gaps (validator checks that none
    overlaps).
  - M4 stripes cross the footprint (54 soft hits at the chosen anchor). This is soft, because all pins
    are on M1.
  - DF.13/14 estimate: worst cell point to well tie 9.52 µm, within the 15 µm limit, using the same-row or
    well-sharing-neighbour tap, 3.92 µm vertical (`validation_run.log`). The TT flow does not check
    DF.13/14 (§7).
- **Legal chip anchors:** 56 (rows 1..37, clear of taps and endcaps, site ≡ 17 mod 70, row even).
  Chosen: row 6, site 157 (x 91.28–130.48, y 27.44–117.60).
- **Ports** (composition contract, `placement.json: ports`):
  - West: S_in[i] and M[i] in relative row i, facing mac_unit's S flop (source) and its S load mux (M consumer).
  - North: first and en into the decode row (controller above).
  - Clock: CLK at sdffq x 5.88–6.44 in each row.
  - The chain is internal, running south to north; nothing on the east side.

### 5.2 `b_m` / `b_ms` sub-placements (`out/b_m/`, `out/b_ms/`)
- `b_m`: 29 × 22 = 16.24 × 86.24 µm, 100% inside a 33-site window (4 spare sites per row). 1,360 legal
  anchors; 0 taps inside.
- `b_ms`: 64 × 22 = 35.84 × 86.24 µm, 90.6% (11 taps at rel site 33–34 in alternate rows). 256 legal
  anchors (site ≡ 2 mod 35).
- Ports:
  - `b_ms`: S column west (Q → adder a, exp_lut, compare; D ← mac sum and load mux), M column east
    (Q → compare and S load mux).
  - `b_m`: the side Q faces is chosen by the mirror search.
- Names are bound to one synthesized netlist (`names.json`: path and sha256), per §3.2.

### 5.3 Generator and validator
- **`gen_placement.py`** is the single source: netlists, chip RTL, placement CSV/JSON/SVG,
  `MACRO_PLACEMENT_CFG` lines, `names.json`, Phase 4 block inputs and `MANIFEST.json` (input and output
  hashes). `--check` is the stale check. `--anchor V=ROW,SITE` and `--names-netlist` re-target the output.
- **`validate_placement.py` → ALL_OK** (`validation.json`, `validation_run.log`). Its checks:
  - stale outputs;
  - every view (netlist, CSV, JSON, cfg) agrees with the others, and the chip-RTL bodies equal the netlists;
  - geometry and row parity, taps and endcaps, inside rows 1..37;
  - intent: bit per row, one-row chain hops, chain input on A1, gt on oai21 A1, flop names bound to their Q nets;
  - connectivity and Liberty function;
  - LEF widths and pin access;
  - DF.13/14 estimate;
  - **slew rule:** no combinational master with an ss transition of 2.7 ns or more at [3][3].
- **Self-test:** 10 deliberately illegal inputs, each of which must fire its intended check:
  overlap, off-grid, orientation, tap overlap, outside rows 1..37, chain broken, chain moved off A1,
  gt moved off A1, slow `aoi222_1` substituted, names swapped. All 10 pass.

## 6. LibreLane mechanisms (measured here)
- `MACRO_PLACEMENT_CFG` on std cells: FIXED from step 17 to the final DEF (b_m, b_ms, a_sdff).
- Fixed cells are still visible to repair_design, which upsizes them in place
  (`aoi222_1` → `aoi222_4`/`_2`, 30 log entries) and then fails DPL-0033 on the overlaps. Mitigation in this plan:
  slew-legal masters (validator) and explicit drivers (`buf_4` on SE).
- `RSZ_DONT_TOUCH_RX` was not used: ripple_add measured that it breaks repair (RSZ-3006).
- `MANUAL_GLOBAL_PLACEMENTS` is rejected (drift, ripple_add).
- The define route (`VERILOG_DEFINES` with `ifdef`) and the direct netlist route give the same synthesis
  (a_sdff harden synth 39,829.7 = `ll_synth`).

## 7. Phase 4 plan

### 7.1 Standalone block (evidence and characterization; a_sdff is not adopted in the chip)
1. **Inputs** (generated, untested): `out/max_reg_a_sdff.v`, `out/a_sdff/block.cfg` (FIRM lines in block
   coordinates), `block_pins.cfg` (W: S_in/M interleaved bottom to top; N: first, en; S: clk) and
   `block_librelane.json`:
   - die 57.12 × 113.68 µm;
   - core 90 sites × 27 rows from (3.36, 3.92);
   - footprint at block site 17 and block row 2;
   - `FP_TAPCELL_DIST` 20 (chip value), so the tool's taps should land at the chip phase (0 / 35 mod 70),
     that is rel sites 53 and 18. Rows 0–1 and 25–26 stay free for the dense boundary taps;
   - `SYNTH_ELABORATE_ONLY`, repair off, `PL_OPTIMIZE_MIRRORING` off, M2–M4 routing, KLayout DRC on.

   Stated deviations: PDN stripe phase and die-edge ports.
2. **Asserts after each step:**
   - ManualMacroPlacement: 109 FIXED exact (`check_placed.py` with the block cfg);
   - TapEndcap: taps exactly at the chip phase, no overlap with a FIXED cell, and endcaps on all rows.
     If the phase differs, place fillties FIXED from `placement.json: taps_inside`;
   - after CTS and any repair: masters unchanged (the §6 failure mode);
   - after routing: only M2–M4, every net routed, 0 DRT violations.
3. **DRC:**
   - Magic, plus the KLayout full deck (`gf180mcu.drc`, `feol=true beol=true offgrid=true run_mode=deep`);
   - **DF.13_MV and DF.14_MV reported explicitly**, on the block and once in chip context on a window of the
     `a_sdff` chip GDS (`/Users/samuelzhang/ttharden/mr3_a_sdff/runs/wokwi/final/gds`) around x 91–131,
     y 27–118, because neither Magic nor the TT flow checks them;
   - any finding inside a cell is compared with the PDK cell's standalone reference (addf_1 gives 4 DF.13/14
     items standalone) before it is attributed to placement.
4. **LVS:** Netgen against `max_reg_a_sdff.v`, and also the KLayout LVS deck.
5. **Extraction:** OpenRCX SPEF at nom, min and max. Magic extraction to SPICE.
6. **Characterization:**
   - OpenSTA with SPEF at tt, ss and ff: clk→M; S_in[0] → chain → gt → nld → SE setup (the block's
     critical arc); SI hold (Q→SI self-loop); the buf_4 SE spine slew; transitions against 3 ns;
   - ngspice-47 (host) on the extracted critical path with the PDK models (`libs.tech/ngspice`),
     compared against STA;
   - switched capacitance per net class (chain, S_in, SE spine, clock), with annotated activity: random
     first, then the controller pattern from the contract's `sim_ctrl` mode.
7. **Views:** GDS, pin-only LEF, Liberty timing model (OpenSTA `write_timing_model`), DEF, SPEF, the netlist.

### 7.2 In-chip integration
- **Decision:** keep (c). If the orchestrator wants max_reg in the whole-chip tetris anyway:
  1. Co-place it with mac_unit: S register, adder bit-slice, S load mux and exp_lut taps. Never as a stand-alone
     column (§2.4).
  2. Name mechanism: harvest names by Q net from the run's own synthesized netlist (§3.2), or
     `max_reg_b_flopcells.v` behind an `ifdef` for stable names (§3.3).
  3. Integrate with `MACRO_PLACEMENT_CFG` (FIRM), only for slew-legal cells, with `check_placed.py` on every
     step DEF.
  4. Accept only on shipped-flow metrics against the noise band: area, 9-corner WNS/hold,
     slew/cap/fanout, power, wire, DRC/LVS. Add a KLayout DF.13/14 window check.
- **For `a_sdff`, if ever revived:**
  1. Regenerate at a new anchor with `gen_placement.py --anchor a_sdff=R,S`. There are 56 legal anchors,
     with the site ≡ 17 mod 70 and even-row rule.
  2. Set `VERILOG_DEFINES: ["MAX_REG_CELLS"]` and `MACRO_PLACEMENT_CFG` to `out/a_sdff/chip_anchor.cfg`.
  3. Rerun `contract_chip_rtl`. The measured run is `chip_runs/a_sdff`.

## 8. Risks
1. **Context loss and obstruction (measured):** a frozen max_reg loses ABC's folding, about +550 µm² in
   synthesis **(estimate of the mechanism)**, and displaces its neighbours (+11 mm wire).
2. **Fixed cells are resizable:** a FIXED cell that repair wants to upsize breaks DPL. Every fixed
   netlist needs the slew rule. A future rule change, such as a tighter `MAX_TRANSITION_CONSTRAINT`,
   invalidates the check.
3. **Name fragility:** 11 of 26 netlists renumber the flops. A cfg made for one netlist silently
   targets the wrong cells on another, unless the Q-net check runs (§3.2).
4. **Critical-path coupling:** constraining M or S moves the ss worst path onto the mac adder → S[21]
   (−2.7 to −7.4 ns). This must be solved in the mac_unit phase.
5. **Noise samples:** the band has only 3 golden hardens. The `b_*` deltas are pure placement effects
   on an identical netlist, which is the cleanest comparison available, but one placement perturbation
   is still a single sample.
6. **Power is vectorless.** The block's +0.30 mW combinational increase is not a workload measurement.
   Phase 4 needs VCD power (ripple_add notes X propagation from unreset flops in gate-level simulation).
7. **`sdffq_1` is in `no_synth.cells`.** The PDK's reason is not stated. Synthesis area reports miss it,
   so always use `statdiff.py`. DRC and LVS were clean in the chip run, but KLayout DF.13/14 was not checked.
8. **DF.13/14** compliance is a geometric estimate (9.52 µm) until Phase 4 KLayout.

## 9. File index (`pd_flow/modules/max_reg/layout_plan/`)
- `PLAN.md`, `tables.md` (generated), `validation.json`, `validation_run.log`, `census.json`.
- `gen_placement.py`, `validate_placement.py`.
- `out/`: netlists, chip RTL, `a_sdff/`, `b_m/`, `b_ms/`, `MANIFEST.json`.
- `contract_a_sdff/`, `contract_chip_rtl/`, `contract_b_flopcells/`, and their `*.runlog` files.
- `chip_runs/`:
  - `{b_m,b_ms,a_sdff}/` (overlay, cfg, `harden/`, `placement_check.json`);
  - `a_sdff_aoi222_FAILED/`;
  - `syn_*/rtl`, `synth_stat/`, `logs/`;
  - `harden_table.{json,txt}`, `netlen.{json,log}`.
- `ctx/`, `names/`, `evidence/` (arcs, LEF census log), `superseded/`.
- `tools/`:
  - from ripple_add: `harden.sh`, `scrape_harden.py`, `defparse.py`, `lefcensus.py`, `cellfun.py`;
  - new: `check_placed.py`, `ctxmap.py`, `flopnames.py`, `netlen.py`, `statdiff.py`, `arcs.py`, `make_tables.py`.
