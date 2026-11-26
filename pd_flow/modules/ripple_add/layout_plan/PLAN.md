# ripple_add: Phase 3 layout plan (Agent 4, layout architect)

Date: 2026-11-26. Scope (D4/D5): placement of existing GF180 7-track cells only, automatic
routing, a relative sub-placement that composes into the whole-chip tetris placement.
Nothing in `src/`, the reference project or the PDK was edited. Nothing was committed.
Every number below comes from a run in this directory; the source file is named next to it.
Estimates are marked **(estimate)**.

**Revision 2 (after independent review, `../layout_review/REVIEW.md`).** B1: the MSB carry is now
fixed on xor3_1 A3 (the fast input); the earlier generator had put it on A1, and runs `final*`
carried that penalty. N1–N6/N10 are addressed in place: tap rule, estimate labels, rejected
`MANUAL_GLOBAL_PLACEMENTS` output, a dedicated `RIPPLE_ADD_CELLS` guard (RTL contract 68/68),
soft stripe preference, block-config deviations, and a self-test that must hit its intended check.

## 0. Verdict

1. **Shipped chip: keep the golden RTL. ABC maps it in context.** Every cell-level
   implementation was measured in the shipped flow, with the adder frozen as cells inside the
   `ripple_add` boundary, and none of them improves the chip:
   - synthesis gains at most 0.5%;
   - harden std-cell area does not drop (it stays inside the cosmetic-noise band or rises);
   - setup WNS at ss falls by 15.7 ns (hybrid, carry on A3) and more for the other variants;
   - max-cap violations rise from 1 to 2–3;
   - vectorless power rises by 12–18%.

   The cause is the context: in the shipped flow ABC merges mac_unit's operand logic
   (`b = neg ? ~term : term`, the `a` mux, and the constants of the N=12 instance) into the
   adder. A frozen adder cannot absorb that logic: roughly 770 µm² **(estimate)** comes back
   as mux2 and inverter cells (§2.3).
2. **Tetris track: the cell-level implementation to place is the hybrid**
   `addf_1 × (N−1) + xor3_1` on the MSB (no carry out; carry on the fast input A3). It is placed as one bit per row,
   in a column 33 sites wide by N rows. Among the frozen implementations it is the best or
   equal-best on every axis:
   - module area −26.8% (N=22) and −26.2% (N=12);
   - switched pin capacitance −30%;
   - the smallest chip synthesis area of the frozen candidates that keep both widths;
   - carry delay the same as a pure addf chain, slightly better.

   Both netlists pass the frozen contract in gate mode (10/10, 11/11). The placement
   generator and validator are complete (G0 and G1 passed). **It should be adopted only
   together with the mac_unit bit-slice.** The mac_unit phase has to co-structure the operand
   logic (above all the `neg` conditional inversion) to recover the context loss, and it has
   to accept the measured timing cost (§3).
3. **Placement mechanism (measured):**
   - `MANUAL_GLOBAL_PLACEMENTS` is **rejected**: it is a hint only. Cells stay PLACED. Detailed placement
     mirrored 21 of 34 cells and moved 2. In the final DEF, 2 of 34 cells are off their
     target, by up to 20.7 µm.
   - `MACRO_PLACEMENT_CFG` (step `Odb.ManualMacroPlacement`) also works on std cells. It
     fixes them at step 17, before taps and global placement. Result: 34 of 34 cells at
     their exact target in every later DEF, masters unchanged, DRC and LVS clean. Re-measured
     on the corrected netlist (run `fixed_a3`): ss WNS 25.26 ns (−16.5 ns against base),
     std-cell area 47,040.9 µm² (inside the noise band), slew/cap/fanout 399/0/11,
     3.599 mW vectorless.
   - `RSZ_DONT_TOUCH_RX` on the adder instances breaks `RepairDesignPostGPL` (RSZ-3006).
     Do not use it.

## 1. Method and evidence locations

| What | How | Evidence |
|---|---|---|
| Library facts | Tokenizer LEF parse with asserts (`lefcensus.py`): site `GF018hv5v_mcu_sc7` 0.56 × 3.92 µm, grid 0.005, M1/M3 horizontal and M2/M4 vertical (pitch 0.56), M5 horizontal (pitch 0.90), tracks.info offset 0.28 | `census.json`, `out/census_summary.json` (LEF sha256 `47dadf84…`, tech LEF `1e15a88b…`) |
| Chip context | Baseline DEF: 39 rows × 607 sites, core origin (3.36, 3.92), row 0 N and rows alternating N/FS; FIXED taps (filltie, 2 sites) every 39.2 µm, checkerboard with a 19.6 µm offset, dense taps on rows 0 and 38; M4 PDN pairs VPWR x = 19.68 + 38.87k, VGND x = 22.98 + 38.87k, 1.6 µm wide, no M5 | `gen_placement.py: chip_context()` (asserts), `out/census_summary.json` |
| Module level | Explore netlists (`explore/make_explore.py`); OpenSTA in librelane:3.0.14 with the Phase 2 boundary (0.30 ns slew, 0.02 pF load, no wire), plus `report_power` at input activity 0.5/cycle; switched pin capacitance from a Liberty-function evaluator (`cellfun.py`) on 4,000 random vectors, zero-delay and unit-delay | `explore/sta/*.log`, `explore/activity.json`, `explore/activity.log` |
| Chip synthesis | `pd_flow/scripts/ll_synth.sh` on `chip_runs/<tag>/rtl` (7 shipped files, only `ripple_add.v` replaced, made by `tools/make_variant_rtl.py`) | `chip_runs/logs/llsynth_<tag>.txt`, `chip_runs/synth_stat/<tag>.stat.json`, run dirs `/Users/samuelzhang/ttharden/llsynth/ra_<tag>` |
| Chip harden | `tools/harden.sh`: copies `/Users/samuelzhang/ttharden/attention_head_gf` to `/Users/samuelzhang/ttharden/ra_<tag>` (without `runs/`), replaces the RTL, merges an optional overlay into the mirror's `src/config.json`, then runs `tt/tt_tool.py --pdk gf180mcuD --harden`. One run at a time, 66–85 s each | `chip_runs/<tag>/harden/` (metrics.json, resolved.json, final DEF/nl/pnl, gzipped STA reports for all 9 corners, step DEFs, `tt_tool_harden.log`, SHA256SUMS); `chip_runs/logs/harden_<tag>.txt`; full run trees in `/Users/samuelzhang/ttharden/ra_<tag>/runs/wokwi` |
| Tables | Generated from raw outputs by `tools/make_tables.py` (not transcribed) | `tables.md`, `chip_runs/harden_table.{json,txt}` (`tools/scrape_harden.py`) |

## 2. Candidates and judgement

### 2.1 Module level (from `tables.md`)

| N=22 | Cells | Area µm² | a/b/cin→s TT ns | SS ns | Power TT µW | Switched pin C fF/vec (zero / unit delay) |
|---|---:|---:|---:|---:|---:|---:|
| ABC-mapped (default ABC, Phase 1 netlist) | 95 | 2146.91 | 10.594 | 21.319 | 138.7 | 498.4 / 543.3 |
| pure addf_1 chain | 22 | 1593.72 | 19.908 | 41.429 | 115.8 | 356.0 / 400.5 |
| **hybrid addf_1 + xor3_1 MSB** | 22 | **1571.76** | 19.280 | 40.127 | **115.0** | **348.6 / 392.7** |
| addf_2 chain + xor3_1 | 22 | 1710.06 | 18.762 | 38.754 | 147.9 | 352.4 / 396.6 |
| addf_1/addf_2 alternating + xor3_1 | 22 | 1637.62 | 19.037 | 39.483 | 130.8 | 350.4 / 394.6 |

N=12 results have the same ranking: hybrid 847.35 µm², 10.545 / 21.893 ns, 61.0 µW, 186.7 fF,
against ABC at 1148.09 µm², 6.100 / 12.231 ns, 73.1 µW, 264.6 fF. All netlists pass the
evaluator's function check (4,000 vectors, against `a+b+cin`).

- **Area:** the hybrid is the smallest. The xor3_1 MSB (50.49 µm²) replaces an addf_1
  (72.44 µm²) whose carry out is unused.
- **Carry delay:** every addf chain is about 1.9× slower than the oai21/aoi21 chain. addf_1
  CI→CO is about 0.9 ns TT and about 1.8 ns SS per bit, and the CO slew is 0.71 ns at SS
  with only about 10 fF of load. addf_2 gains only 2.7% (N=22 SS) for +29% internal power,
  so it is rejected. The alternating mix sits in between and is also rejected.
- **Power (module):**
  - switched receiver-pin capacitance is −30% against ABC;
  - OpenSTA total is −17%;
  - the unit-delay/zero-delay ratio is 1.13 for addf chains and 1.09 for ABC. This is an
    indicator only (synchronous unit delay, not a timing model). Glitching is slightly
    higher in relative terms, lower in absolute terms.

### 2.2 Chip level (shipped flow; measured; noise band from cosmetic RTL variants)

| Variant | Synth µm² | Std-cell µm² | Util | Setup WNS ss / tt / ff ns | Hold WNS ss / tt / ff ns | Slew / Cap / Fanout | Power mW |
|---|---:|---:|---:|---|---|---|---:|
| **base** (golden, re-run = stored baseline) | 41,116.1 | 46,819.2 | 90.09% | 41.79 / 70.72 / 76.06 | 1.136 / 0.415 / 0.109 | 381 / 1 / 11 | 3.050 |
| n03 (golden, cosmetic) | 41,100.7 | 46,990.5 | 90.42% | 38.21 / 68.89 / 75.39 | 1.160 / 0.428 / 0.119 | 316 / **2** / **13** | 2.971 |
| n04 (golden, cosmetic) | 41,201.7 | 47,220.9 | 90.87% | 42.90 / 71.72 / 75.29 | 1.241 / 0.469 / 0.142 | 260 / 1 / 11 | 3.220 |
| ABC netlists frozen as cells | 41,972.2 | 48,037.6 | 92.44% | 41.37 / 70.92 / 75.36 | 1.232 / 0.465 / 0.140 | 311 / 1 / **14** | 3.758 |
| pure addf_1 (both) | 41,056.8 | 47,010.2 | 90.46% | 25.08 / 63.46 / 75.55 | 1.189 / 0.442 / 0.125 | 287 / **3** / 11 | 3.435 |
| **hybrid (both widths, carry on A3)** | 41,012.9 | 46,926.8 | 90.30% | 26.12 / 63.95 / 75.59 | 1.194 / 0.446 / 0.129 | 287 / **3** / 10 | 3.421 |
| determinism check: hybrid rerun with generate label renamed | 41,012.9 | 46,926.8 | 90.30% | bit-identical to hybrid | identical | identical | 3.421 |
| hybrid N=22 only, N=12 ABC | 40,922.9 | 47,471.2 | 91.35% | 19.20 / 60.28 / 75.97 | 1.113 / 0.404 / 0.104 | 269 / **3** / **12** | 3.559 |
| final (superseded generator: carry on xor3 **A1**) | 41,012.9 | 47,001.4 | 90.44% | 23.69 / 62.75 / 75.35 | 1.201 / 0.450 / 0.132 | 308 / **2** / 11 | 3.443 |
| final (A1) + MANUAL_GLOBAL_PLACEMENTS (rejected) | 41,012.9 | 46,979.5 | 90.40% | 23.46 / 62.68 / 75.51 | 1.188 / 0.443 / 0.128 | **418 / 3 / 13** | 3.821 |
| final (A1) + MACRO_PLACEMENT_CFG (FIRM) | 41,012.9 | 46,997.0 | 90.44% | 23.16 / 62.58 / 75.53 | 1.155 / 0.425 / 0.116 | **414** / 0 / **12** | 3.611 |
| **fixed_a3: current RTL (carry on A3, `RIPPLE_ADD_CELLS`) + MACRO_PLACEMENT_CFG (FIRM)** | 41,012.9 | 47,040.9 | 90.52% | 25.26 / 63.58 / 75.56 | 1.188 / 0.441 / 0.126 | **399** / 0 / 11 | 3.599 |

Bold marks counts above the baseline's 381/1/11. The `fixed_a3` synthesis figure comes from the
harden's own Yosys step (`chip_runs/fixed_a3/harden/synth_stat.json`), because `ll_synth.sh`
does not pass the define; it equals `hyb`'s `ll_synth` result (41,012.92 µm², 1,313 cells). Every run has 0 setup and 0 hold
violations, 0 route DRC, 0 Magic DRC and 0 LVS errors. Corner columns are the `max_*` RC
corners; the full 9-corner data is in `chip_runs/harden_table.txt`. Power is LibreLane's
vectorless STA at nom TT (internal and switching split in `tables.md`).

Reading the table:
- **Noise.** Cosmetic rewrites of the golden RTL (n03, n04) move:
  - std-cell area by +171 to +402 µm²;
  - ss WNS from 38.2 to 42.9 ns;
  - power from 2.97 to 3.22 mW;
  - cap / fanout counts up to 2 / 13.

  The baseline is the most favourable member of its own family. The flow is deterministic:
  rerunning the hybrid with only a generate label renamed (hybcos) is bit-identical. hyb
  against final is **not** noise: the RTLs differ in the MSB pin assignment (carry on A3
  against A1). The xor3 arc on the ss worst path is 1.597 ns (A3) against 3.545 ns (A1),
  which accounts for 1.95 ns of the 2.43 ns WNS difference
  (`chip_runs/hyb/harden/sta_postpnr/max_ss_125C_3v00/max.rpt.gz` against
  `chip_runs/final/...`; `../layout_review/msb_arc_evidence.txt`). **The
  "must not exceed 381/1/11" rule is broken by cosmetic noise alone** (n03: cap 2,
  fanout 13).
- **Area:** hybrid synthesis −103 µm² (−0.25%). Harden std-cell area is +107.6 µm² (hyb),
  inside the noise band, so area is unchanged within the measurement (pure addf_1 and the
  other hybrid runs are also inside it). The frozen ABC netlist is +1,218 µm², outside the noise.
- **Timing:** the hybrid (carry on A3) loses **15.7 ns** of ss WNS, about 3× the band width,
  so outside noise. The final/final_* runs lose 18.1–18.6 ns because they also carry the A1 penalty. The ss critical path
  runs from the control decode through the term mux and `neg` XOR into `bitslice[0].B`, then
  up the whole chain (`chip_runs/hyb/harden/sta_postpnr/max_ss_125C_3v00/max.rpt.gz`).
  +26.1 ns of slack remains at 100 ns (hyb). Hold is unaffected.
- **Electrical rule counts:**
  - max-cap 2–3 against 1 for every cell variant except FIRM, which gets 0;
  - fanout and slew counts are within noise, except for the two placed probes, where slew is
    399–418 because the column sat far from its drivers (§5.6).
- **Power:** +12% vectorless (3.42–3.44 mW), above the noise band. Combinational internal
  power rises 0.46 → 0.63 mW (`chip_runs/<tag>/harden/sta_postpnr/nom_tt_025C_3v30/power.rpt.gz`).
  The frozen ABC netlist rises by the same mechanism (+0.30 mW combinational), so the cause
  is freezing the module boundary, not the addf cell itself. Vectorless activity propagation
  is not a workload: see the risk register in §8.

### 2.3 Why the module-level win disappears in context (synthesis cell diff, `chip_runs/synth_stat/*.stat.json`)

Hybrid against base, per cell family (all drive strengths together):
- removed: −70 nand2, −59 oai21, −34 xor2, −18 or2, −13 nor2, −11 aoi21, −9 nor3, −7 xnor2, −5 xor3 net (the 2 xor3_1 MSBs included), and others;
- added: +34 mux2, +30 clkinv, +11 aoi222, +5 tiel, +32 addf.

The module-level saving is 575 + 301 = 876 µm² (default-ABC module netlists). The chip-level
synthesis saving is only 103 µm². The difference, about 773 µm², is an **estimate** of what comes
back as surrounding logic: it subtracts two different area measures (module default ABC against
in-context shipped-flow ABC). The cell-family diff above supports the mechanism:
- `b = neg ? ~term : term` is now built explicitly (mux2 plus inverter) instead of being
  merged into the adder's XOR;
- the N=12 instance's constants (`cin=0`, `b[11:8]=0`, `a = first ? 0 : L`) can no longer
  be folded: 5 tie cells, 4 addf with B tied low.

## 3. Chosen implementation and conditions

**Implementation:** `bitslice[i].u_fa` = addf_1 for i = 0..N−2 (A=a[i], B=b[i], CI=c[i],
S=s[i], CO=c[i+1]), and `u_msb_x3` = xor3_1 for bit N−1 with **A3 = c[N−1]** (fixed, fast
input), A2 = a[N−1], A1 = b[N−1] (a/b chosen by pin access, §5.3). The design uses N=22 and N=12.

**Why:**
- it is the smallest frozen cell netlist, with the lowest switched capacitance and the
  shortest addf carry;
- its instance names are stable and match the flattened chip names exactly
  (`core.mac.adder.bitslice[3].u_fa`, checked in the synthesized netlist and in ODB);
- its chip synthesis area is the lowest of the candidates that freeze both widths (pure addf_1,
  frozen ABC). Harden area does not separate it from pure addf_1: both are inside the noise band.

Pure addf_1 is dominated (larger and slower). The frozen ABC netlist costs +1.2k µm².
"N=22 cells, N=12 ABC" cannot be placed as a sub-placement (its N=12 names are unstable) and
measured worst on timing and power.

**Conditions for adoption (gate for the mac_unit phase):**
1. Recover the context loss. Put `neg` handling and the a-mux into the mac bit-slice as
   explicit cells that sit beside the column. Candidate structure: one xor2 or xnor2 per bit
   on the term, or the conditional inversion folded into the term mux. Measure that against
   the in-context ABC baseline.
2. Accept the setup cost of −15.7 ns at ss (hyb), or buy it back.
   The reviewer's upper bound (`../layout_review/REVIEW.md` N4, Liberty areas, estimate): even
   with co-design the area gain is at most about 1% of std-cell area, about the size of the noise
   band. The mac_unit phase should also compare against a placement-only alternative that keeps
   ABC's in-context mapping and only regions or clusters it.
3. Bring the cap count back to ≤ 1, or get the orchestrator to re-rule the threshold given
   the noise.
4. **N=12 (estimate, Liberty areas only):** the generic N=12 netlist wastes its constant inputs. An
   instance-specialized L adder for `cin=0, b[11:8]=0` would use:
   - addh_1 for bit 0;
   - 7 addf_1 for bits 1–7;
   - 3 addh_1 for bits 8–10;
   - xor2_1 for bit 11.

   That is 691.5 µm² against 847.35 µm² for the generic hybrid (Liberty areas, not run). It
   needs a mac_unit change and its own contract, because it is not `a+b+cin` for all inputs.

## 4. Netlists (deliverable 2)

`out/ripple_add_n22.v` and `out/ripple_add_n12.v` hold `module ripple_add` with no
parameter and a generate loop of cell instances, so names are identical to the chip
flattening. `out/ripple_add_chip.v` is the parameterized chip RTL: the cell branch is under
`` `ifdef RIPPLE_ADD_CELLS `` (set only through `VERILOG_DEFINES` in the harden config) and the
golden body is in `` `else ``, so every simulator, linter and default synthesis sees the golden body.

Frozen contract, hash `b879560878477abf` (re-verified after the B1 change: 17/17 files OK
against `CONTRACT.sha256`). All three runs were redone on the B1-corrected outputs:

| Run | Command | Result |
|---|---|---|
| N=22 netlist | `verif/run_all.sh --rtl layout_plan/out/ripple_add_n22.v --gate 22 --out layout_plan/contract_n22` | **10/10**. proven: prove and abc pdr. covered: 16/16. pass-sampled: vectors and random. negative control failed as expected. lint: 0 warnings |
| N=12 netlist | same with `--gate 12 --out layout_plan/contract_n12` | **11/11**, including pass-exhaustive 2^25 |
| chip RTL (define off) | `verif/run_all.sh --rtl layout_plan/out/ripple_add_chip.v --out layout_plan/contract_chip_rtl` | **68/68**, all_ok. (The earlier `SYNTHESIS` guard failed the 8 lint items, because Yosys defines `SYNTHESIS` and then saw the cell branch) |

`results.json` `dut_sha256` equals the current `out/` files. The current chip RTL is
`chip_runs/fixed_a3/rtl/ripple_add.v`; with the define on it was hardened as run `fixed_a3`
(§2.2), overlay `chip_runs/fixed_a3/overlay.json` = `MACRO_PLACEMENT_CFG` + `VERILOG_DEFINES`.

The validator separately evaluates the emitted netlists cell by cell from Liberty functions:
N=12 exhaustively (2^25), N=22 on 2^20 random vectors plus 176 carry patterns. Outputs and
the carry bus have 0 mismatches against numpy integer addition (`validation_run.log`).

## 5. Coordinate-level placement (deliverable 3)

### 5.1 Grammar and footprint
Ripple-chain grammar: **bit i is relative row i**, and every addf_1 is at relative site 0,
which gives one column. The MSB xor3_1 is at relative site 10, mirrored.

| | N=22 | N=12 |
|---|---|---|
| Footprint | 33 sites × 22 rows = 18.48 × 86.24 µm | 33 × 12 = 18.48 × 47.04 µm |
| Bounding box / cell area | 1,593.72 / 1,571.76 µm² | 869.30 / 847.35 µm² |
| Utilization (site-rows) | 716 / 726 = **98.62%** | 386 / 396 = 97.47% |
| Free sites | top row, relative sites 0–9 (10 sites) | same |

Bounds (`placement_n22.json: bounds`):
- the area floor and the feasibility floor at 22 rows are both 33 sites, equal to the widest
  cell, so **the column is the bound**;
- at 11 rows the floor is 66 sites, at 8 rows 99, at 4 rows 198;
- unfolded into one row, the adder needs 716 sites, more than the core's 607.

A separate pure-Tetris bound placement is not needed, because the wire-aware seed already
meets the bound.

### 5.2 Orientation and rails
- Rows alternate N/FS from chip row 0 (N), so a relative row's orientation depends on the
  anchor-row parity. The CSV carries both `orient_even_anchor` and `orient_odd_anchor`.
  addf_1 uses the row-native orientation (N or FS). The xor3_1 is mirrored (FN or S).
  Both masters have `SYMMETRY X Y`.
- VDD and VSS are Metal1 `SHAPE ABUTMENT` pins (LEF), so they join the follow-pin rails by
  abutment. No cell has Metal2 or higher shapes.
- Power hookup to the Metal4 stripes (pitch 38.87 µm, 1.6 µm wide): the default anchors put
  the column between stripe pairs (x 63.28–81.76 µm, between the k=1 pair at 58.55/61.85 and
  the k=2 pair at 97.42/100.72). The rails reach the stripes outside the column, and the
  M1→M4 via stacks sit at stripe x, so they never land on adder pins.
- 272 legal anchors exist for N=22 (the hard rule: inside the core, no FIXED tap or endcap).
  128 of them are also stripe-free (sites 37, 107, …, 527, rows 1–16). Stripe-free is only a
  **soft preference**: every pin is on Metal1 and the stripes cross every row anyway, so it must
  not shrink the tetris search space.
- **Taps (the binding constraint):** the chip's FIXED filltie checkerboard leaves free
  windows exactly 33 sites (18.48 µm) wide: [24.08 + 39.2k, 42.56 + 39.2k] and
  [43.68 + 39.2k, 62.16 + 39.2k]. That is exactly the addf_1 width. At the default anchor,
  even rows have a tap abutting the column's west edge and odd rows have one abutting its
  east edge. The 5 V library rule DF.13_MV/DF.14_MV allows at most **15 µm** to a well tie, and
  the same-row tap alone is up to about 19 µm away. Compliance therefore relies on the
  **staggered tap in the well-sharing neighbour row**; the reviewer measured a worst case of
  10.3 µm per well (`../layout_review/check_coords.log`). Consequences: a column must never sit
  in a row whose well-sharing neighbour lacks the staggered tap, and since the TT flow runs no
  KLayout DRC and Magic does not check DF.13/14, a clean harden is not evidence of compliance
  (Phase 4 adds the check, §7). Rows 0 and 38 have dense taps and are excluded.

### 5.3 Pin accessibility (census, `census.json`)
Access points are on-grid Via1 positions (Via1 M1 enclosure 0.38 × 0.26 or 0.26 × 0.38,
taken from the tech-LEF VIA section and asserted) wholly inside the pin's own Metal1, on M2
tracks (x = 0.28 + 0.56k in cell coordinates).

| Master | Pin access tracks (count) |
|---|---|
| addf_1 | A 3, B 4, CI 3 (x 12.60–13.72), CO 1 (x 17.64), S 1 (x 0.28) |
| xor3_1 | A1 4, A2 5, A3 5, Z 4 |

- Every access pad (M2 0.28 wide) lies at least 0.14 µm inside the cell outline, so an
  abutting neighbour's pads are always at least 0.28 µm away (M2 spacing). **No pin can be
  blocked by abutment** (validator check 8).
- The CI horizontal bar (0.23 µm tall) is too thin for a via. CI is reached only through its
  wider 12.34–13.91 µm part.
- **Pin-equivalence rule:** pin access may choose only among inputs that are equivalent in
  timing and energy, not merely logically interchangeable. The full adder is logically symmetric
  in A, B and CI; the carry stays on CI, which has the lowest capacitance (9.42 fF against
  11.56 / 11.24 fF) and the fastest arc. On the xor3_1, A3 feeds only the last XOR stage: A3→Z is
  the fast arc (Liberty ss about 0.3–1.5 ns against 1.4–3.4 ns for A1/A2), and a glitching carry
  there toggles fewer internal nodes. The carry is therefore fixed on A3, and the generator
  searches only 11 slides × 2 mirrors × 2 a/b assignments over {A1, A2}, with the HPWL proxy as
  tie-breaker (`gen_placement.py: search_msb`). (Revision 1 searched all 6 permutations on HPWL
  alone and put the carry on A1: review finding B1.)

### 5.4 Routing-resource census (`placement_n22.json: routing_census`)
- M1 is for pin access and rails only (`RT_MIN_LAYER` Metal2). M2, M3 and M4 are through
  tracks over every cell.
- Per row: 33 M2 tracks, 7 M3 tracks, 33 M4 tracks. In-footprint M3 demand is about 2 per
  row (a/s stubs west, the b stub and the carry jog east), leaving **5 of 7 M3 tracks free**
  for chip feed-through **(estimate before routing)**.
- The scarce direction is horizontal (M3), because the column is one cell wide.
- **Carry hop:** CO (x 17.64) to CI (x 13.72) in the next row, 3.92 µm across and about
  3.9 µm up. Proxy about 8.5 µm per hop, 178.0 µm for 21 hops (172 µm before B1; the A3 pin sits farther from CO) (HPWL from pin access points,
  `hpwl_proxy_*`). A 7-site stagger would align CO over CI, but only as a staircase.
  Alternating N/FN does not help (the misalignment comes back on the next hop), so it was
  not adopted.
- **Measured in the chip (FIRM probe, ss max path):** mean CO net load fell from 13.1 fF
  (free placement, hyb) to 10.8 fF (column, fixed_a3; 10.7 fF in final_fixed). With CI at
  9.42 fF, the wire share of that load went from 28% to 13% (derived), and the mean CI→CO delay
  from 2.053 to 1.977 ns per hop (`chip_runs/{hyb,fixed_a3}/harden/sta_postpnr/max_ss_125C_3v00/max.rpt.gz`).
  The MSB arc on that path is A3→Z 1.647 ns in fixed_a3, against A1→Z 3.585 ns in final_fixed.
  In the final netlist of fixed_a3, `u_msb_x3.A3` is driven by `c[N−1]` for both instances.

### 5.5 Composition contract (relative sub-placement)
| Field | Value |
|---|---|
| Footprint | 33 × N sites/rows, rectangular. The top row is ragged: 10 free sites on the west |
| West ports | `a[i]`, `s[i]` in relative row i (accumulator side: the S register and ring head feeding `a`; `sum` going back to S and the ring tail) |
| East ports | `b[i]` in relative row i (operand side: term shift mux and `neg` inversion) |
| South port | `cin` at row 0 (`neg` for N=22; constant 0 for N=12) |
| North | none (no carry out) |
| Pin order | bottom to top = bit order. One row per bit, matching a 22-row mac bit-slice (ring flop, S flop, a-mux on the west; term mux on the east) |
| Anchor rules | row parity sets orientation; rows 1..(38−N); x window between taps (site ≡ 37 mod 70 for stripe-free, else tap-legal per `legal_chip_anchors`) |
| Default anchors | N=22 (row 1, site 107); N=12 (row 23, site 107), stacked above. Placeholders until the mac_unit phase places the bit-slice |

In the baseline placement, the mac ring flops are scattered over most of the die, with medians in the lower left (read from the baseline DEF with `tools/defparse.py`; the scatter is not quantified here). Port sides therefore follow the
logical sources, and the anchor has to be chosen together with the mac bit-slice.

### 5.6 Generator and validator
- `gen_placement.py` is the single source. Its outputs in `out/`: the netlists, the chip RTL,
  the placement CSV/JSON/SVG, the chip anchors as `MACRO_PLACEMENT_CFG` lines
  (`chip_anchor_n*.cfg`, the integration input), the same coordinates as reference JSON
  (`chip_anchor_n*.json`, key `placement` plus a "do not use as MANUAL_GLOBAL_PLACEMENTS"
  status, so it cannot be pasted into a config), the Phase 4 block views, and a MANIFEST with
  input and output hashes.
  - `--check` is the stale check.
  - It refuses to write a non-default anchor over the frozen `out/`.
- `validate_placement.py` covers checks 1–9 of experiments.md §5. Result: **ALL_OK**
  (`out/validation.json`, `validation_run.log`). The self-test feeds 8 deliberately illegal
  inputs, and a case counts only if its **intended** check fires (rejection by another check
  does not count): overlap, off-grid, wrong width, orientation against row parity, tap overlap,
  outside core (anchor at site 590 in rows 1–12, past the 607-site row and clear of tap rows),
  a broken carry chain, and the carry moved off A3. All 8 pass.
- What placement alone costs: the FIRM probe with the column at the placeholder anchor gives
  route wirelength 59,779 µm (fixed_a3) against 50,789 µm free (hyb), and slew 399, and it
  costs 0.86 ns of ss WNS against free-placed hyb. This is the method's
  warning that an isolated block is a diagnostic: the column has to be co-placed with its
  bit-slice before area, power or timing can be judged.

## 6. LibreLane placement mechanisms (librelane 3.0.14 source, then measured)

| | `MANUAL_GLOBAL_PLACEMENTS` (`Odb.ManualGlobalPlacement`, `scripts/odbpy/placers.py`): **REJECTED** | `MACRO_PLACEMENT_CFG` (`Odb.ManualMacroPlacement`, same file) |
|---|---|---|
| Format | config dict `{"<verilog hierarchical name>": {"location": [x, y] (µm, absolute die), "orientation": "N/FS/FN/S"}}`. Names are bracket-escaped automatically. Unknown names are an error | text lines `name x y orient`. Gridified to 5 DBU. Deprecated in favour of `MACROS`, but works |
| Step and status | step 33, after GlobalPlacement and RepairDesignPostGPL, before DetailedPlacement. Sets **PLACED** | step 17, before CutRows, TapEndcap, PDN and GPL. Sets **FIRM** (`--fixed`). No macro-class filter, so it applies to std cells |
| Measured (`chip_runs/placement_effect.json`) | after step 33: 34/34 exact. After DPL: 11/34 exact (21 mirrored by `PL_OPTIMIZE_MIRRORING`, 2 xor3 moved 10.6–14 µm). Final: 32/34 exact (max 20.7 µm) | after step 17, after DPL and in the final DEF, in both final_fixed and fixed_a3: **34/34 exact, FIXED**. Masters unchanged (no resize). 348 taps as in base, so no tap conflict. DRC, LVS, antenna and PDN violations 0 |

`RSZ_DONT_TOUCH_RX="^core\.mac\.(l_)?adder\."` together with FIRM placement makes
RepairDesignPostGPL fail. The log reads "RSZ-3006 Failed to insert buffer before loads for
net core.exponent_unit.W[5]", because a load pin is dont_touch
(`chip_runs/final_fixed_donttouch/`). It is not needed: FIRM cells were not resized.

## 7. Phase 4 plan

### Standalone block (G2–G3), one run per width, N=22 first
1. Inputs, all generated: `out/ripple_add_n22.v`, `out/block_n22.cfg` (FIRM lines in block
   coordinates), `out/block_n22_pins.cfg` (S: cin; W: a[i], s[i] interleaved, bottom to top;
   E: b[i]), and `out/block_n22_librelane.json` (an **untested** starting config):
   - die 27.44 × 94.08 µm;
   - core (3.36, 3.92)–(24.08, 90.16), 37 sites × 22 rows (2-site endcap, 33-site column,
     2-site endcap);
   - `SYNTH_ELABORATE_ONLY`;
   - CTS and all resizer steps off;
   - `PL_OPTIMIZE_MIRRORING` off;
   - Metal2–Metal4 routing, KLayout DRC on.

   Two deviations from chip context are stated at the top of the config (`//deviation_*` keys):
   - **PDN:** the block is 27.44 µm wide, less than the 38.87 µm stripe pitch, so one Metal4
     VPWR/VGND pair lies over the column (the chip anchors are stripe-free). It is harmless for
     function but removes M4 tracks, so routing comparisons with the chip must note it.
   - **Taps:** `FP_TAPCELL_DIST` 100 means no taps inside the block; the only well ties are the
     2-site endcaps at both row ends. The farthest column point is about 9.5 µm from an endcap,
     within the 15 µm DF.13_MV/DF.14_MV limit (estimate from geometry; to be confirmed by DRC).
2. Assert after each step:
   - after `ManualMacroPlacement`: 22 FIRM instances at the exact coordinates (adapt
     `tools/check_placed.py`);
   - after `TapEndcapInsertion`: no tap inside the core and endcaps at both ends of all 22 rows;
   - if GPL refuses an all-fixed design, `--skip` the GPL steps and record that too;
   - after routing: no wire outside Metal2–Metal4, and every signal net routed.
3. Route with routing automatic, then classify any failure per routing-closure §3. The only
   expected pressure is M3 at the carry jog and b stub (the estimate in §5.4).
4. Sign-off: Magic and KLayout DRC (full deck, `run_mode=deep`, **`feol=true`**), Netgen LVS
   against the netlist, RCX/SPEF at nom/min/max. **DF.13_MV/DF.14_MV (well-tie distance ≤ 15 µm)
   must be reported explicitly:** once on the block, and once in chip context on a window around
   the placed column, because neither Magic nor the TT flow checks it. Any DRC finding inside a cell must be compared against a standalone DRC run of the bare PDK cell (Phase 0 reference) before it is attributed to placement.
5. Characterization with OpenSTA and SPEF, at TT, SS and FF:
   - a/b/cin→s delays per bit;
   - the carry wire share (target ≤ 12%, as measured in the chip probe);
   - power with annotated activity (random, then the mac workload).

   SPICE is blocked (no ngspice/Xyce, PHASE0).
6. Repeated object (G4): abut two copies east–west, and a column stacked above a column,
   then rerun DRC and LVS.

### Chip integration (after the mac_unit phase decides)
1. The mac_unit phase places its bit-slice around the column and picks the anchor from
   `legal_chip_anchors*`. Regenerate with `gen_placement.py --anchor22 R,S --anchor12 R,S
   --out <run dir>`.
2. Guard (done): the cell branch is under `` `ifdef RIPPLE_ADD_CELLS ``, enabled by
   `"VERILOG_DEFINES": ["RIPPLE_ADD_CELLS"]` in `src/config.json`. The RTL contract passes
   68/68 with the define off, and run `fixed_a3` is the measurement with it on. LibreLane's lint
   step also receives the define and passes because it blackboxes the PDK cell models.
3. Fix the cells with `MACRO_PLACEMENT_CFG` and `out/chip_anchor_n*.cfg` (FIRM, measured to
   hold), not `MANUAL_GLOBAL_PLACEMENTS` (rejected: measured to drift). Do not set `RSZ_DONT_TOUCH_RX` on the cells.
4. Accept only on shipped-flow metrics against the noise band in §2.2:
   - std-cell area;
   - WNS and hold for all 9 corners;
   - slew, cap and fanout counts;
   - power;
   - DRC and LVS.

## 8. Open risks
1. **Context loss.** In isolation the frozen adder is worse for the chip. The gain depends
   entirely on mac_unit co-design (§3), and that is not yet shown.
2. **Timing.** −15.7 ns at ss for the hybrid with the carry on A3 (WNS +26.1 ns left; hyb),
   −16.5 ns with the column fixed at the placeholder anchor (fixed_a3).
   Later module changes share this margin.
3. **Rule counts.** Cap 2–3 against 1 for free-placed cell variants. Cosmetic golden
   variants also exceed 381/1/11 (n03: 2/13), so the threshold needs an orchestrator ruling
   on noise.
4. **Power is vectorless only.**
   - +12% (outside noise) and attributed to combinational internal power.
   - Workload-annotated power was attempted: the project's top test on the base gate-level
     netlist with functional cell models produces X from the deliberately unreset datapath
     flops and fails (`chip_power/gl_top_test_base_probe.log`, "Cannot convert Logic('X')
     to int").
   - Phase 4 needs flop initialization (deposit at t=0) or a 2-state simulator before VCD
     power.
5. **Taps.** Anchors are limited to 33-site windows between FIXED taps. In whole-chip tetris
   the tap strategy becomes a placement decision (taps can join the grammar).
6. **Unit-delay glitch figures are indicative only.** The OpenSTA module power is zero-delay
   and probabilistic.
7. **N=12 generic netlist** carries tied-off inputs. Specialization needs a mac_unit change
   (estimate in §3).
8. **Harden noise.** The flow is deterministic (hybcos = hyb, bit-identical). Perturbation
   sensitivity is measured only by n03/n04 (area +171 to +402 µm², ss WNS 38.2–42.9 ns). The
   2.4 ns hyb/final difference is a real pin-swap effect, not noise (§2.2). No delta smaller than
   the band is attributable.
9. **N=12 tie cells.** The FIRM run has 5 `tiel` cells in the N=12 adder name space, placed by
   the tool outside the column. The sub-placement is not self-contained until N=12 is specialized.

## 9. File index (`pd_flow/modules/ripple_add/layout_plan/`)
- `PLAN.md`, `tables.md`.
- `gen_placement.py`, `validate_placement.py`, `lefcensus.py`, `cellfun.py`.
- `out/`: generated handoff and `validation.json`.
- `census.json`, `validation_run.log`.
- `contract_n22/`, `contract_n12/`, `contract_chip_rtl/` (and their `*.runlog`).
- `explore/`: module-level netlists, STA, activity.
- `chip_runs/<tag>/{rtl,harden}`, `chip_runs/logs/`, `chip_runs/synth_stat/`,
  `chip_runs/harden_table.*`, `chip_runs/placement_effect.json`.
- `chip_power/`.
- `tools/`: `make_variant_rtl.py`, `harden.sh`, `scrape_harden.py`, `make_tables.py`,
  `check_placed.py`, `defparse.py`.
