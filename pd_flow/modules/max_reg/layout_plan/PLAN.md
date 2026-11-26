# max_reg: Phase 3 layout plan (Agent 4, layout architect), revision 2

Date: 2026-11-26.

**What revision 2 adds** over revision 1:
- review round 1 (`../layout_review/REVIEW.md`: B1, B2, N1–N4);
- user decision D6 (`pd_flow/AGENT_CONTEXT.md`, "Area-first ranking"): rank by area; timing is only a
  legality check (WNS ≥ 0 and hold met at every corner on the 100 ns clock).

**Scope** (D4/D5): placement of existing GF180 7-track cells only, automatic routing, and a relative
sub-placement that composes into the whole-chip tetris.

**Ground rules:**
- Nothing in `src/`, the reference project or the PDK was edited. Nothing was committed.
- No chip harden was run in revision 2; the 4-harden budget was spent in revision 1.
- Every number comes from a run in this directory, and its source is named. Estimates are marked **(estimate)**.
- `tables.md` is generated from the raw outputs by `tools/make_tables.py`.

## 0. Verdict

### 0.1 Shipped chip: keep (c), free placement of the golden RTL
Ranked by chip std-cell area, with timing and the D2 band as legality checks
(`tables.md`, "D6 ranking"; raw `metrics.json` of each run):

| Rank | Run (full harden) | Std-cell µm² | Δ | Setup/hold at all corners | Slew/cap/fanout against the D2 band | Legal under D6 |
|---:|---|---:|---:|---|---|---|
| 1 | (b) `b_m`: 22 M flops fixed | 46,784.1 | −35.1 | pass | **cap 4 > 2** | no |
| 2 | **(c) baseline, free** | **46,819.2** | 0 | pass | inside (381/1/11) | **yes** |
| 3 | (b) `b_ms`: M + S flops fixed | 46,909.2 | +90.0 | pass | **slew 388 > 381, cap 3 > 2** | no |
| 4 | (a) `a_sdff` v1: fixed block | 48,151.7 | **+1,332.5** | pass | **slew 418 > 381** | no |

- **Noise band** (3 golden hardens: base, n03, n04): std-cell area 46,819.2–47,220.9 µm².
- **`b_m`**:
  - **Area:** 35 µm² below the baseline. That is under 10% of the band's width (402 µm²), from a single run,
    so it is not a measurable gain.
  - **Same netlist:** its synthesized netlist is byte-identical to the baseline's.
  - **Where the area moved:** logic +35.2 and clock buffers +35.1; clock inverters −57.1 and repair −48.3.
    That is resizer and CTS reshuffling, not a placement saving.
  - **Not legal:** it adds 2 cap violations beyond the D2 band.
- **`b_ms` and `a_sdff` v1** are larger and outside the D2 band.

The free baseline is therefore both the smallest legal result and the recommendation. Every run is clean at
signoff (route DRC, Magic DRC, LVS and antenna all 0). The baseline's absolute ss WNS (41.79 ns) and power
(3.050 mW) now matter only as legality and context.

### 0.2 Why the (b) column variants do not save area
- **No synthesis change.** `b_m` and `b_ms` only move flops. The area classes that can change are
  repair, clock tree and resizer upsizing, which total about 3,800 µm² per D6.
- **The free placer already does well here.** It already puts the 22 M and 22 S flops in a ring around
  their shared logic (mean M–S distance 17.9 µm, `ctx/base_ctx.json`).
- **A straight column adds wire** (`chip_runs/netlen.log`):

  | Variant | max_reg nets | Rest of chip |
  |---|---:|---:|
  | `b_m` | +0.9 mm | +1.9 mm |
  | `b_ms` | +3.8 mm | +5.0 mm |

- **The extra wire did not buy area.**
  - Repair: `b_m` −48 µm², `b_ms` +18 µm². Both are inside the golden spread, which is +242 to +277 µm²
    in n03/n04.
  - DRV: the extra wire raised cap counts above the band.

### 0.3 Timing (B2; legality only under D6)
Corrected from revision 1. The claim "fixing M/S moves the critical path onto mac_unit's adder" was wrong.

- The `config_chain` → mac_unit adder → S[21] (`core.exponent_unit.D[21]`) path is **co-critical in every
  golden harden**: second in base (41.95 against 41.79 ns), second in n03 (39.69 against 38.21 ns), and the
  worst path in n04 (42.90 ns). Source: `../layout_review/pathclass.log`.
- **`b_m`:**
  - WNS is 39.14 ns, inside the golden WNS band (38.21–42.90).
  - The −2.81 ns change on that path is diffuse displacement of mac_unit's datapath
    (`../layout_review/s21_path_evidence.txt`):
    - clk→Q +0.5 ns;
    - front end +1.0 ns, through a repair `dlyb_1` (`wire11`, 3.47 ns);
    - carry chain +1.7 ns;
    - the tail through the M-fed load mux −0.38 ns (faster).
  - None of it runs through a pin of the fixed M flops.
  - It is comparable to golden n03 (−2.27 ns on the same path with no constraint, partly through a 7.27 ns
    `dlyb_1`).
- **`b_ms`:** −5.82 ns on that path (carry chain +3.6 ns). This is the only timing delta outside the band,
  and it is one sample.
- Reports: `chip_runs/{b_m,b_ms}/harden/sta_postpnr/max_ss_125C_3v00/max.rpt.gz`, and n03 under ripple_add.
- Under D6 all four runs are timing-legal (setup and hold met at every corner).

### 0.4 Coupling argument (restated from facts that hold)
- M feeds mac_unit's S load mux, and S feeds max_reg's compare.
- The 22 S flops are the mac adder's own register.
- Any joint M/S placement therefore has to be done together with the mac_unit bit-slice. The orchestrator
  ruling to tetris at mac_unit bit-slice level stands on its own and does not need a critical-path claim.

### 0.5 The a_sdff block
- **v1 (hardened):** +548.8 µm² in synthesis and +1,332.5 µm² in the chip. By class against the baseline:

  | Class | Δ µm² | Cause |
  |---|---:|---|
  | seq | +428 | sdffq_1 replaces dffq_1 |
  | logic | +228 | |
  | inv | +180 | |
  | repair | +439 | |
  | buf | +31 | |

  The block's own cells (2,952.5 µm²) equal ABC's in-context max_reg (2,954.7 µm²). The loss is in how the rest
  of the chip is mapped and repaired. Rest-of-chip wire grew by 11.1 mm.
- **v2 (§5, this revision):**
  - Rebuilt for the minimum footprint: **3,042.6 µm² box, against 3,534.3 (−13.9%)**.
  - Cell area **2,939.4, against 2,952.5 µm²**.
  - Cells plus chip taps fill 99.8% of the box.
  - Fanout-legal and slew-legal by the new validator rule.
  - Shipped-flow synthesis +535.6 µm², still outside the synthesis band (−52.7 / +234.9;
    `chip_runs/synth_stat/statdiff_v2.txt`).
  - Not hardened.
  - It does not change the chip decision. It is the Phase 4 standalone object.

### 0.6 Power (N2, corrected)
- Revision 1 put a_sdff v1's +0.30 mW combinational increase down to "the chain toggling every SCORE clock".
  Vectorless activity cannot show that.
- The reviewer's OpenSTA run (nom_tt, nom SPEF, vectorless; `../layout_review/sta_power/`) gives:

  | Cells | Count | Power µW |
  |---|---:|---:|
  | a_sdff block cells | 109 | 76.9 |
  | golden cone + M flops, in base | 134 | 77.7 |

- The chip increase is therefore **outside** max_reg: displaced wiring, ABC's remapping and repair buffers.
- Under D6, power is context only.

## 1. Method and evidence

| What | How | Evidence |
|---|---|---|
| Library | LEF census (`tools/lefcensus.py`): site 0.56 × 3.92; M1/M3 horizontal, M2/M4 vertical; pitch 0.56; pin access per master. Now also inv_2 and inv_3. Liberty arcs per pin (`tools/arcs.py`) | `census.json`, `evidence/lefcensus.log`, `evidence/arcs_ss_summary.txt` |
| Chip context | Baseline DEF: 39 rows × 607 sites; FIXED fillties at site 0 mod 70 in odd rows and 35 mod 70 in even rows (asserted) | `gen_placement.chip_context` |
| Chip limits | `MAX_FANOUT_CONSTRAINT` 20, `MAX_TRANSITION_CONSTRAINT` 3 ns, `DESIGN_REPAIR_MAX_SLEW_PCT` 10, `MAX_CAPACITANCE_CONSTRAINT` 0.2 pF | `pd_flow/baseline/harden/resolved.json`, read by the validator |
| Minimum footprint | `tools/pack_search.py`: exhaustive search over width, tap phase, row parity, 1/2/3 bits per row, and any row for bit 0 + decode | `evidence/pack_search.{log,json}` |
| Context maps | `tools/ctxmap.py` (M/S flops, exclusive cone, M–S distance, Q/D HPWL) | `ctx/*_ctx.json` |
| Flop names | `tools/flopnames.py` over 26 shipped-flow netlists | `names/stability.json` |
| Synthesis | `pd_flow/scripts/ll_synth.sh`, `tools/statdiff.py` (adds the unknown sdffq area back from the Liberty) | `chip_runs/synth_stat/`, `chip_runs/logs/llsynth_*.txt` |
| Harden (revision 1) | `tools/harden.sh` → `tt_tool.py --harden` in `/Users/samuelzhang/ttharden/mr3_<tag>`, one at a time | `chip_runs/<tag>/harden/` |
| Placement held | `tools/check_placed.py` (step 17, GPL, DPL, final; plus CTS for b_ms and a_sdff). The reviewer's `check_fixed.py` covers all 16 DEFs per run (N4) | `chip_runs/<tag>/placement_check.json`, `../layout_review/check_fixed.log` |
| Wire attribution | `tools/netlen.py` (routed DEF segments by net class) | `chip_runs/netlen.{log,json}` |
| Tables | `tools/make_tables.py` | `tables.md` |

## 2. Options

### 2.1 (a) Fixed bit-sliced block
- **v1** (hardened, `superseded/v1_se22/out/`, `chip_runs/a_sdff/`):
  - 109 cells, 70 × 23 sites (39.20 × 90.16 µm), 83.5% cell utilization;
  - one `buf_4` drove all 22 SE pins.
- **B1, measured** (review; `../layout_review/a_sdff_se_fanout_evidence.txt`):
  - Fanout 22 is above `MAX_FANOUT_CONSTRAINT` 20.
  - RepairDesignPostGPL therefore inserted a free `dlyb_1` (`fanout1`, at (128.24, 98.0)) **inside** the frozen
    block. It drives 20 SE pins at 6.74 ns ss transition against the 3 ns limit.
  - That accounts for 20 of the 37 slew violations a_sdff v1 adds over the baseline, plus one repair cell's area.
- **The netlist did not hold.**
  - What held: 109/109 FIXED cells at exact coordinates with masters unchanged.
  - What did not: a 110th cell was inserted on a block net.
  - Revision 1 wrongly called this "held", and wrongly called the `buf_4` a mitigation.
- **v2** (`out/`) fixes it (§5): the SE is split, two inverters drive 11 loads each, and a drive rule is enforced.

### 2.2 (b) Placement-only (ABC's in-context logic free)
- `b_m`: 22 M flops in one 29-site column at anchor row 6, site 177.
- `b_ms`: S flop i at rel site 0 and M flop i at rel site 35, from row 6, site 142.
- Both are measured in §0. The anchor proxy already ranked the column below the free ring (estimate):

  | Variant | Proxy HPWL at chosen anchor | Free baseline positions |
  |---|---:|---:|
  | `b_m` | 2,213 µm | 951 µm |
  | `b_ms` | 5,056 µm | 2,820 µm |

### 2.3 (c) Free placement
The shipped result. The flow is deterministic: the `b_*` step-6 netlists are byte-identical to the baseline's
(`a339bf99…`, reviewer sha256).

## 3. Flop instance names (option b)
- **Stability** (`names/stability.json`):
  - Yosys numbers the M flops `_2277_`…`_2298_` in the baseline.
  - The names are identical for identical input, and in 15 of 26 netlists.
  - They are renumbered in 11 of 26 (n03, n05, n06, g_v2, g_v4, g_v5, c01, c10, and three ripple_add hardens).
  - The names are always contiguous and in bit order. The Q nets (`core.mac.M[k]`, `core.exponent_unit.D[k]`)
    never change.
- **How to fix only the flops:**
  1. Map Q net → instance in a synthesized netlist of exactly this RTL and config (`gen_placement.py --names-netlist`).
  2. Write `MACRO_PLACEMENT_CFG` lines from that map.
  3. Post-check every step DEF by Q net (`tools/check_placed.py`).
  - Wording fix (N4): `out/b_*/names.json` binds the **baseline final netlist**
    (`pd_flow/baseline/harden/nl/…nl.v`, sha256 `a8286e1b…`), not the step-6 synthesis netlist (`a339bf99…`).
    The M/S flop names are identical in both, and in the harden's own step 6.
  - Results: b_m 22/22 and b_ms 44/44 held at every step DEF (the reviewer's 16-DEF check). The CTS DEF is
    missing from `chip_runs/b_m/placement_check.json` but is covered there.
- **Stable-name alternative:** `out/max_reg_b_flopcells.v`, the flops as explicit `dffq_1 bNN_ff` cells with the
  next state left behavioural.
  - Contract (gate mode) 19/19 (`contract_b_flopcells/`).
  - Synthesis 41,048.0 µm². That is −68.1 against base, **15.4 µm² below the lowest golden synthesis sample**
    (41,063.4), which is not a confirmed gain (N4).
  - Not adopted. Use it only if the whole-chip tetris needs names that survive edits.

## 4. Netlist (deliverable 2)

| File | Content | Contract (`verif/run_all.sh`, frozen hash `6d7f5b5ff9a94fc9`, 16/16 files OK) |
|---|---|---|
| `out/max_reg_a_sdff.v` (v2, sha256 `8acb5872…`) | 109 cells: 22 `sdffq_1`; 21 × (`inv_1`, `nand2_1`, `nor2_1`); 11 `oai21_1` + 10 `aoi21_1` chain; decode `oai21_1` + 2 × `inv_2`. 2,939.4 µm² | `--gate`: **19/19**, including `eqy_rtl` proven, k-induction/pdr, covers and vectors (`contract_a_sdff/`, `contract_a_sdff.runlog`, 96.7 s) |
| `out/max_reg_chip.v` (sha256 `efdd9a53…`) | golden module under `` `else ``, the v2 body under `` `ifdef MAX_REG_CELLS `` | RTL mode, define off: **17/17** (`contract_chip_rtl/`) |
| `out/max_reg_b_flopcells.v` | §3 | `--gate`: 19/19 (`contract_b_flopcells/`) |
| `superseded/v1_se22/out/max_reg_a_sdff.v` (v1, `78a8967f…`, hardened) | buf_4 SE spine (B1) | `--gate` 19/19 (`superseded/v1_se22/contract_a_sdff/`; rerun by the reviewer) |

The validator's own function check evaluates the v2 netlist cell by cell from the Liberty functions. Over
262,208 vectors it finds 0 mismatches against the golden signed rule, with ties allowed to load.

## 5. Coordinate-level placement (deliverable 3): a_sdff v2

### 5.1 Minimum footprint (D6)
**Cell sites to place:** 1,339 = 22 × 38 (sdffq_1) + 21 × 23 (stage) + 20 (decode).

**Search** (`tools/pack_search.py`, `evidence/pack_search.log`):
- **What it searches:** every footprint width; every chip tap phase (anchor site mod 70) and row parity; 1, 2 or 3
  bits per row; and any row for bit 0 together with the decode.
- **Feasibility test:** exact packing of each row's cells into its tap-free segments.

**Result:**
- The minimum box is **1,386 site-rows**, the same for 1 bit per row (63 × 22) and 2 bits per row (126 × 11).
  3 bits per row needs 1,520 (190 × 8).
- Fewer than 22 rows is impossible below 76 sites of width, because two 38-site flops cannot share a row.
- With 22 rows, the 22 chip taps leave 1,342 site-rows at width 62, but no packing exists there that keeps
  each bit's cells in one row. 63 is the smallest width that does.
- **Chosen: 63 sites × 22 rows (35.28 × 86.24 µm), one bit per row.** This keeps the bit-sliced intent.

| Version | Box | Cell area | Cell sites / box | (cells + taps) / box |
|---|---:|---:|---:|---:|
| v1 | 70 × 23 = 1,610 site-rows, 3,534.3 µm² | 2,952.5 µm² | 83.5% | 86.4% |
| **v2** | **63 × 22 = 1,386 site-rows, 3,042.6 µm²** | **2,939.4 µm²** | **96.6%** | **99.8%** (3 free sites) |

Changes from v1:
- **No gt inverter.** The chain polarity is flipped so that it ends in true gt. Stage 1 starts from M[0], which
  is the tie don't-care, valid because S_in == M loads an equal value.
- **No decode row.** The decode sits in bit 0's row, since bit 0 has no compare stage.
- **D and SI swapped.** D = M (hold), SI = S_in (load), so SE is active-high ld. That lets two `inv_2` drive SE.
- **SE split for B1.** Two nets of 11 loads each (`ld_lo`: rows 0–10, `ld_hi`: rows 11–21), against v1's
  `inv_1` + `buf_4` on 22 pins.
- **Smallest legal cells.** Every function uses its `_1` size. The `inv_2` drivers are the smallest drivers
  that meet the drive rule: `oai21_1` driving an 11-load SE net directly was estimated at 7.9–8.9 ns and failed.

### 5.2 Row templates (anchor site ≡ 17 mod 70, anchor row even)
In the chip, the tap sits at rel site 18–19 in even rows and 53–54 in odd rows, and every bit row is exactly full.

| Row | West → east (rel sites) |
|---|---|
| even | inv 0, nor2 4, chain 10, (tap 18), nand2 20, sdffq 25 (63/63) |
| odd | sdffq 0, inv 38, nand2 42, nor2 47, (tap 53), chain 55 (63/63) |
| row 11 (bit 0) | sdffq 0, `u_ld` oai21_1 38, `u_se_lo` inv_2 46, (52 free), (tap 53), `u_se_hi` inv_2 55, (61–62 free) |

Bit placement:
- Bits 1–11 are in rows 0–10, bit 0 is in row 11, and bits 12–21 are in rows 12–21.
- Placing bit 0 in the middle keeps gt (row 20 → 11) and both SE spines short.
- The chain hops one row, except from bit 11 to bit 12, where it hops over the decode row. The validator
  accepts that skip only over a row that holds no compare stage.

Chain cells sit on opposite sides in alternate rows (rel 10 / 55), so each hop is about 25 µm. Under D6,
area outranks this wire.

### 5.3 Drive rule (B1)
**What the validator checks** on every block-driven net:
- fanout ≤ 20;
- load ≤ min(the driver's max_capacitance, 0.2 pF);
- estimated ss transition < 2.7 ns, at the worst legal input slew (3 ns).

**Model inputs (estimate):**
- Load = Liberty pin caps + wire. Wire is 1.25 × the rectilinear MST of the pin access points × 0.20 fF/µm.
- That is calibrated against the v1 chip SPEF, which gives 0.167–0.181 fF/µm on the measured SE nets.

**Worst v2 nets:**

| Net | Driver | Fanout | Load | Est. transition |
|---|---|---:|---:|---:|
| `nld` | `u_ld` oai21_1 | 2 | 20.7 fF | 2.41 ns |
| `ld_hi` | `u_se_hi` inv_2 | 11 | 91.6 fF | 2.33 ns |
| `ld_lo` | `u_se_lo` inv_2 | 11 | 90.4 fF | 2.31 ns |
| `gt` | `b21_cmp` oai21_1 | 1 | 17.0 fF | 2.14 ns |

The v1 netlist fails the rule with "fanout 22 > 20 on net nld_b". Source: `validation_run.log`.

### 5.4 Chip anchors, pins, power and wells
- **Legal chip anchors:** 64. Rows 1..37, clear of taps and endcaps, site ≡ 17 mod 70, even row.
- **Chosen anchor:** row 6, site 157. The HPWL proxy (estimate) gives 3,080 µm external and 1,151 µm internal.
- **Pin access:** every signal pin has an on-grid Via1 point at least 0.28 µm inside the cell (`census.json`).
  For example, `inv_2` I and ZN have 3 each.
- **Power:** VDD/VSS are M1 abutment rails, and no cell has M2+ shapes.
- **PDN:** 55 soft M4-stripe hits at the chosen anchor. They are soft because all pins are on M1.
- **DF.13/14 estimate:** 9.52 µm, within the 15 µm limit, using the well-sharing neighbour row's tap. Measured
  on the same-row tap alone, it is up to 18.5 µm (reviewer, `../layout_review/welltie.log`). In the
  whole-chip tetris, keep the rule that a block sits where its neighbour row has the staggered tap.
- **Ports:** see `out/a_sdff/placement.json: ports`.
  - S_in[i] and M[i] are in bit i's row.
  - first and en go into `u_ld` in row 11.
  - The chain is internal.

### 5.5 Generator and validator
- **`gen_placement.py`** is the single source of every view. `--check` reports FRESH.
- **`validate_placement.py`** reports **ALL_OK** (`validation.json`, `validation_run.log`). Its checks:
  - views agree;
  - geometry and taps;
  - intent: one row per bit, ascending; chain on A1; stage 1 from M[0]; stage 21 drives gt; gt on A1;
  - slew rule and the new drive rule;
  - function: 262,208 vectors;
  - LEF and pin access;
  - DF.13/14.
- **Self-tests:** 12, now matched on the **specific message** (N1). Two are new:
  - "v1 SE: one driver on 22 SE pins" must fire "fanout 22 > 20";
  - a fanout-legal 20-load SE must fire "est. ss transition".
- **Mutation check** (`tools/selftest_mutation.py`, adapted from the reviewer's; `evidence/selftest_mutation.log`):
  - with each targeted check disabled, its self-test turns BAD and no other self-test changes;
  - result: **12/12** (`ALL_SELFTESTS_DEPEND_ON_THEIR_CHECK`).

## 6. LibreLane mechanisms (measured)
- `MACRO_PLACEMENT_CFG` on std cells keeps them FIXED, at their location, from step 17 to the final DEF.
- It does **not** freeze the netlist:
  - **Resizing:** repair_design resizes FIXED cells in place. In v0, `aoi222_1` was resized to `aoi222_4`/`_2`,
    30 log entries, followed by DPL-0033 (`chip_runs/a_sdff_aoi222_FAILED/`).
  - **Buffer insertion:** it also inserts buffers on block nets. In v1, a `dlyb_1` fanout buffer went onto SE
    (B1).
- Both are prevented only by a netlist the repair has no reason to touch:
  - slew rule: master transition;
  - drive rule: fanout, load and net transition.
- `RSZ_DONT_TOUCH_RX` is not used: it breaks repair (RSZ-3006, ripple_add).
- `MANUAL_GLOBAL_PLACEMENTS` is rejected: its placements drift.

## 7. Phase 4 plan: implement a_sdff v2 standalone, plus one golden control

### 7.1 Block run
Inputs are generated but untested: `out/max_reg_a_sdff.v`, `out/a_sdff/block.cfg`, `block_pins.cfg` and
`block_librelane.json`.

**Die and core:**
- die 53.20 × 109.76 µm;
- core 83 sites × 26 rows from (3.36, 3.92);
- footprint at block site 17 and row 2;
- `FP_TAPCELL_DIST` 20, so the tool's taps should land at the chip phase.

**Chip limits:**
- `MAX_FANOUT_CONSTRAINT` 20;
- `MAX_TRANSITION_CONSTRAINT` 3;
- `MAX_CAPACITANCE_CONSTRAINT` 0.2.

**Repair:** design repair (post-GPL and post-GRT) is **on**, as a detector. Timing repair is off (deviation).

**Stated deviations:**
- PDN stripe phase;
- die-edge ports: W carries S_in/M in row order, with first/en at the decode row; S carries clk.

**Asserts after each step:**
1. ManualMacroPlacement: 109 FIXED at exact coordinates (`check_placed.py` with the block cfg).
2. TapEndcap: taps at the chip phase (0 / 35 mod 70), none on a FIXED cell; endcaps on all rows.
   If the phase differs, place fillties FIXED from `placement.json: taps_inside`.
3. **After every repair step: exactly 109 cells, masters unchanged, and no inserted buffer on any block
   net (B1).**
4. Routing: M2–M4 only, 0 DRT violations.

**Signoff and characterization:**
- **DRC:** Magic, plus the KLayout full deck (`feol beol offgrid`, deep). Report **DF.13_MV/DF.14_MV**
  explicitly, on the block and on a window of the v1 chip GDS (`/Users/samuelzhang/ttharden/mr3_a_sdff`).
  Compare cell-internal findings against a standalone reference cell first.
- **LVS:** Netgen and KLayout.
- **Extraction:** OpenRCX SPEF at min, nom and max; Magic extraction to SPICE.
- **Timing:** OpenSTA at tt, ss and ff with SPEF.
  - Report the SE transitions on `ld_lo`/`ld_hi` against the 2.7/3 ns limits, and compare them with §5.3.
    That comparison is the drive-rule calibration check.
  - Report the arcs S_in → chain → gt → nld → inv_2 → SE (setup), and SI/D hold.
  - Timing is legality only.
- **SPICE:** ngspice on the extracted gt → SE path, compared against STA.
- **Views:** GDS, pin-only LEF, Liberty timing model, DEF, SPEF, and the netlist.

### 7.2 Golden control (review round 1, §4.2)
- Config: `out/a_sdff/block_golden_control.json`, untested.
- Same die, core, pins, PDN, taps and limits, with the golden RTL (copied as `max_reg_golden.v`) synthesized and
  placed free. Design and timing repair are on.
- It gives the fixed block's std-cell area **by class**, plus its wire and power, a like-for-like reference.
  The standalone golden mapping is not the in-chip ABC mapping, so state this caveat.
- Report block against control power with the same `sim_ctrl` activity (vectorless shows them equal, N2).

### 7.3 In-chip integration (not recommended for this chip)
- The chip decision stays (c).
- For the whole-chip tetris: co-place max_reg with mac_unit's S register, adder bit-slice and S load mux (§0.4).
- **Name mechanism:** §3.
- **Integration route:** `MACRO_PLACEMENT_CFG` with slew- and drive-legal cells only, and `check_placed.py`
  plus a cell-count assertion on every step DEF.
- **To revive a_sdff v2 in the chip:**
  - `VERILOG_DEFINES: ["MAX_REG_CELLS"]`;
  - `MACRO_PLACEMENT_CFG: out/a_sdff/chip_anchor.cfg`, or another of the 64 anchors via
    `gen_placement.py --anchor a_sdff=R,S`;
  - accept on the D6 table only.

## 8. Risks
1. **Context loss and obstruction (measured on v1).** A frozen max_reg loses ABC's folding: about +536 to
   +549 µm² in synthesis (the mechanism is an estimate). It also displaces its neighbours (+11 mm of wire,
   +439 µm² of repair).
2. **FIXED is not frozen (measured).** The resizer resizes FIXED cells and buffers their nets. Every fixed
   netlist needs the slew and drive rules.
   - The drive rule is an estimate, at 0.3–0.4 ns margin on the SE nets.
   - A tighter `MAX_TRANSITION_CONSTRAINT`, or a calibration miss, invalidates it.
   - Phase 4 STA is the check.
3. **Name fragility.** 11 of 26 netlists renumber the flops. Only a Q-net check makes a cfg safe.
4. **Critical-path coupling (corrected, B2).** The mac adder → S[21] path is co-critical in all golden runs
   and moves by a few ns with any placement perturbation. Only `b_ms` measured outside the band. Under D6 this
   is legality only: all runs keep ≥ 34 ns of ss slack.
5. **Noise samples.** The band is 3 golden hardens. A −35 µm² result (`b_m`) is not resolvable.
6. **Power is vectorless.** It is context only under D6. The block's own share equals the golden cone's (N2).
7. **`sdffq_1` is in `no_synth.cells`.** The PDK gives no reason. Its area is missing from Yosys stat, so use
   `statdiff.py`. DRC/LVS were clean in the chip run; DF.13/14 is still a geometric estimate.
8. **v2 is not hardened.** Its chip-level class breakdown is unknown. On synthesis alone it would cost
   +535.6 µm², so no chip gain is expected.

### Chip-level item for the orchestrator (N3; observation, not acted on)
- Repair uses `dlyb_1` as a buffer: 12–17 per harden, about 25% of repair buffers
  (`../layout_review/repair_buffer_masters.txt`).
- Each one costs 3.5–7.3 ns at ss when it lands on a path.
- It is a mechanism behind harden slack noise, and it is area as well:
  - repair buffers are 1,154.7 µm², one of D6's three physical-design-actionable classes;
  - `dlyb_1` is not the smallest buffer for a pure fanout or slew fix.
- Excluding delay cells from repair buffering is a shipped-config experiment that costs one harden. It is the
  orchestrator's call, not a max_reg change.

## 9. File index (`pd_flow/modules/max_reg/layout_plan/`)
- **Top level:**
  - documents: `PLAN.md`, `tables.md`;
  - validator output: `validation.json`, `validation_run.log`;
  - `census.json`;
  - the generator and validator: `gen_placement.py`, `validate_placement.py`.
- **`out/` (v2):**
  - `max_reg_a_sdff.v`, `max_reg_chip.v`, `max_reg_b_flopcells.v`;
  - `a_sdff/`: placement, `chip_anchor.cfg`, and the block, pins, librelane and golden-control configs;
  - `b_m/`, `b_ms/`;
  - `MANIFEST.json`.
- **Contracts:** `contract_a_sdff/` (v2, 19/19), `contract_chip_rtl/` (17/17), `contract_b_flopcells/` (19/19),
  and their `*.runlog` files.
- **`superseded/`:**
  - `v1_se22/`: v1 outputs as hardened, its contracts and validation, and the v1 census;
  - the aoi222 v0 artifacts.
- **`chip_runs/`:**
  - `{b_m,b_ms,a_sdff}/` (revision-1 hardens) and `a_sdff_aoi222_FAILED/`;
  - `syn_*`, `synth_stat/` (including `mr3s_a_sdff_v2.*` and `statdiff_v2.txt`), `logs/`;
  - `harden_table.*`, `netlen.*`.
- **`evidence/`:** `pack_search.{log,json}`, `selftest_mutation.{log,json}`, `lefcensus.log`, arcs.
- **`ctx/`, `names/`.**
- **`tools/`:**
  - from ripple_add: `harden.sh`, `scrape_harden.py`, `defparse.py`, `lefcensus.py`, `cellfun.py`;
  - new: `check_placed.py`, `ctxmap.py`, `flopnames.py`, `netlen.py`, `statdiff.py`, `arcs.py`, `make_tables.py`,
    `pack_search.py`, `selftest_mutation.py`.
