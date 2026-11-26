# Minimum-drive standard cells (chip_flow_area/min_drive, user direction after D6)

Question: does using the smallest drive variant of every standard cell reduce the shipped chip's area?
The reference is h2 (`../recommended_config.patch`, 45,475.8 µm²).

Scope: golden RTL; flow and PD settings only; nothing changed in `src/`, `tt/`, the PDK or the reference project.

How runs were made:
- Each run is a space-free copy `/Users/samuelzhang/ttharden/md_<tag>` of the golden mirror with h2 plus the
  run's overrides in `src/config.json` (`scripts/run_md.sh`, `overrides/<tag>.json`).
- Screens are partial LibreLane runs, either to `OpenROAD.STAMidPNR-3` (step 43) plus the post-GRT STA proxy, or
  to `OpenROAD.STAPostPNR` (step 55, the routed signoff STA).
- I used partial runs instead of `pilot_dryrun.py`. The experiments change synthesis and the cell lists, and
  `pilot_dryrun.py` restarts from step 17 of a reference run.
- **1 of the 4 allowed full hardens was used (x0_full).** Every run checked `docker ps` first and respected the
  2-container machine limit.

## Result

**Best legal configuration: h2 + mux2_1 allowed (x0). Patch: `recommended_config.patch`, applied on top of h2's
patch, not to `src/`.**

| | Std-cell area | vs h2 |
|---|---:|---:|
| h2 | 45,475.8 µm² | |
| **x0 = h2 + mux2_1 (full harden)** | **44,911.6 µm²** | **−564.2 µm² (−1.24%)** |
| x3 = x0 + clkbuf_16 CTS root (hold-safer, step 55 only) | 45,069.7 µm² | −406.1 µm² |

x0 at signoff (full harden, `runs/full/x0_full`):
- Setup WNS ≥ +43.16 ns and hold WNS ≥ +0.007 ns at all 9 corners; 0 setup and 0 hold violations.
- Slew/cap/fanout 242/1/0, below the D2 ceiling of 381/2/13 and below h2 (281/2/6).
- Power 2.783 mW (h2 2.934 mW, −5.1%).
- In-flow Magic DRC 0, LVS clean ("Circuits match uniquely"), antenna 0, route DRC 0.
- TT precheck KLayout GF180MCU deck 0 and TT antenna deck 0. These were run in Docker with the precheck's PDK
  e8daeda7 and the precheck's options (variant gf180mcuD, deep, 1 thread).
- PDK 54435919 KLayout deck 0, both without and with connectivity rules.
- TT layout checks (top name, forbidden layers, boundary layer, valid layers, cell names): pass.

Area by class (`metrics.json`, µm²):

| Class | h2 | x0 | Δ | x3 |
|---|---:|---:|---:|---:|
| Flops | 20,986.1 | 20,970.7 | −15.4 | 20,970.7 |
| Logic gates | 19,857.8 | 19,625.1 | −232.7 | 19,625.1 |
| Inverters | 763.9 | 724.4 | −39.5 | 724.4 |
| Buffers (synthesis) | 131.7 | 131.7 | 0 | 131.7 |
| Clock buffers | 755.1 | 693.7 | −61.4 | 851.7 |
| Clock inverters | 96.6 | 65.9 | −30.7 | 65.9 |
| Timing-repair buffers | 856.1 | 671.7 | −184.4 | 671.7 |
| Taps + endcaps | 1,870.3 | 1,870.3 | 0 | 1,870.3 |
| Tie cells | 158.1 | 158.1 | 0 | 158.1 |
| **Total** | **45,475.8** | **44,911.6** | **−564.2** | **45,069.7** |

## Starting facts (h2, checked)

- Synthesis already maps every gate to its smallest legal variant. The one exception is 67 `mux2_2`, because
  `mux2_1` is banned by the PDK's `drc_exclude.cells` (together with `oai33_2`).
- Resizer upsizing after synthesis is 47 instances, +781.5 µm².
- A `buf_3` is **21.95 µm²**, not about 9 µm².
  - The smallest repair buffer therefore costs more than most upsizes: 4.4–59.3 µm², 16.6 µm² on average.
  - This is why banning upsizes loses area (Experiment 1).

How LibreLane 3.0.14 applies the cell lists (read in the image's source):
- **Synthesis** excludes `EXTRA_EXCLUDED_CELLS` ∪ `SYNTH_EXCLUDED_CELL_FILE` ∪ `PNR_EXCLUDED_CELL_FILE`
  (`steps/yosys.py:107-109`, `steps/pyosys.py:343-347`).
- **PnR** sets `set_dont_use` on `EXTRA_EXCLUDED_CELLS` ∪ `PNR_EXCLUDED_CELL_FILE` (`steps/openroad.py:333-335`,
  `scripts/openroad/common/io.tcl:408`).
- There is **no PnR-only list**. A design-level `PNR_EXCLUDED_CELL_FILE` replaces the PDK's file (`config/config.py`).
  The list file accepts `#` comments (`common/misc.py: process_list_file`).

Resizer knobs:
- Exposed: `DESIGN_REPAIR_MAX_SLEW_PCT`, `DESIGN_REPAIR_MAX_CAP_PCT`, `DESIGN_REPAIR_MAX_WIRE_LENGTH`,
  `DESIGN_REPAIR_REMOVE_BUFFERS`, `RSZ_DONT_TOUCH_RX`, `RSZ_DONT_TOUCH_LIST`.
- Not exposed: `repair_design -pre_placement` and `-match_cell_footprint`, and `set_opt_config -sizing_area_limit`.

## Experiment 1: no logic upsizing

The step-43 std-cell area equals the final area. m0 and m2 were also taken to step 55: neither area changed after
step 43, and m0 reproduces h2's full harden exactly. Slew/cap/fanout and hold come from the ss/ff proxy at step 43,
or from signoff STA where marked s55.

| Run | Override (on top of h2) | Area | Δ h2 | Logic | Repair | CTS | Resized | Repair bufs | Slew/cap/fo | ff hold |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|
| m0_ctrl | none | 45,475.8 | 0 | 0 | 0 | 0 | 47 | 33 | s55 281/2/6 | s55 +0.058 |
| m1_minall | all 100 above-min logic and flop variants dont-use | 47,284.6 | **+1,808.8** | −728.8 | +2,590.3 | −52.7 | 6 | 157 | 41/0/0 | +0.099 |
| m2_no4 | the 51 drive-≥4 logic and flop variants | 45,403.3 | −72.5 | −300.7 | +285.4 | −57.1 | 45 | 48 | s55 258/2/0 | s55 +0.034 |
| m3_cost | the 29 variants whose upsize costs more than a buf_3 (area over the family's smallest > 21.95) | 45,493.3 | +17.5 | −355.6 | +377.6 | −4.4 | 42 | 51 | 40/0/6 | +0.117 |
| m4_dtrx | `RSZ_DONT_TOUCH_RX "^_[0-9]+_$"` | stopped | **RSZ-3006** | | | | | | | |
| m5_dtlist | `RSZ_DONT_TOUCH_LIST`: the 11 largest h2 upsizes (+441.2) | 46,509.7 | +1,033.9 | −476.4 | +1,532.2 | −22.0 | 33 | 104 | 46/0/5 | +0.109 |
| m6_rmbuf | `DESIGN_REPAIR_REMOVE_BUFFERS` | 45,550.4 | +74.6 | −48.3 | +122.9 | 0 | 47 | 37 | 47/0/6 | +0.119 |

- The synthesis netlist is bit-identical to h2 (`a339bf99…`) in every run. Synthesis already uses the
  smallest variants, so excluding the larger ones from synthesis as well changes nothing.
- **Mechanism (OpenROAD `RepairDesign.cc` at dcf36133):**
  - On a driver-slew violation, `repairDriverSlew` first picks the smallest non-dont-use size that meets the
    limit.
  - If the larger sizes are dont-use, the driver stays weak. `repairNet` then buffers the net along its Steiner
    tree at the load the weak driver can handle.
  - That takes several buf_3 per net. m1 inserts 157 buf_3 for 50 slew and 7 fanout violations; h2 uses 47
    resizes and 33 buffers for 53 and 7.
  - Each upsize that is prevented (16.6 µm² on average) is replaced by roughly 3× its area in buffers. m5 shows
    the same effect on just 11 instances.
- m2's −72.5 µm² is not claimable:
  - It is below the 75 µm² harden noise and far below the 400 µm² bar.
  - Part of it is CTS dummy loads (−57.1).
  - Signoff hold falls to +0.034 ns.
- m4 reproduces the known hazard. Every Yosys-named instance and net becomes dont-touch, and
  `InsertBufferBeforeLoads` fails at RepairDesignPostGPL: "Load pin '_1211_/A2' is dont_touch", RSZ-3006 on
  `core.divider_unit.sum_in[19]`.
- m6: `remove_buffers` deletes the 6 synthesis buffers (RSZ-0026). Logic saves 48.3, but repair then needs 4 more
  buf_4 (+122.9). Net +74.6 µm².
- **Conclusion: banning upsizing increases area in every form tried.** The resizer's upsizing is already the
  cheapest legal repair. Nothing from Experiment 1 goes into the final configuration.

## Experiment 2: mux2_1

### Why it is excluded

- `drc_exclude.cells` has listed `MUX2_X1_7T5P0` and `OAI33_X2_7T5P0` since open_pdks first added GF180MCU
  (`cc0029b45c`, 2022-08-01; the commit gives no reason).
  - The entries were renamed to `mux2_1`/`oai33_2` in `7e4cc7fac3` (2022-08-16).
  - The file moved to `librelane/` in `24f6a0279a` (2026-02-08).
  - The entries have never been re-evaluated.
- The only documented defect is issue google/globalfoundries-pdk-libs-gf180mcu_fd_sc_mcu7t5v0#23 (2022-11-02).
  - Magic reported 2 × "Metal1 overlap of contact < 0.055um in one direction (CO.6)" in mux2_1.
  - The suggested workaround (2022-11-08) was to add the cell to `no_synth.cells` and `drc_exclude.cells`.
  - R. T. Edwards (2022-11-29): Magic's rule simplified GF's CO.6. The real rule is "≥ 0.06 µm in one direction
    if < 0.04 µm in the other", and "the klayout DRC deck should indicate that it's clean".
  - The Magic tech file was fixed the next day: open_pdks `3d8c263c0d`, 2022-11-30, directional surround
    `55` → `55 35`.
  - The issue was closed for inactivity on 2023-04-10.
- Today's `no_synth.cells` lists only `sdff*`. `drc_exclude.cells` still lists mux2_1 and oai33_2.

### DRC evidence (all clean)

DRC was run on:
- the PDK's mux2_1 cell layout;
- synthetic abutment layouts;
- a routed LibreLane test block;
- the chip.

The tools were:
- Magic 8.3.623 with the harden PDK tech, `drc(full)` (the deck in the TT harden flow);
- the PDK 54435919 KLayout deck (FEOL + BEOL + offgrid, deep), with and without connectivity rules;
- the TT precheck deck (PDK e8daeda7 `gf180mcu.drc`, the precheck's options), plus its antenna deck.

| Layout | Magic | PDK KLayout | PDK KLayout + conn | TT deck | TT antenna |
|---|---:|---:|---:|---:|---:|
| mux2_1 alone | 0 | 2 (DF.13_MV, DF.14_MV) | 2 (same) | 2 (same) | 0 |
| mux2_2 alone (control, used by h2) | 0 | 2 (same) | 2 (same) | 2 (same) | 0 |
| addf_1, oai33_1, oai33_2 alone | 0 | DF.13_MV/DF.14_MV only | | same | 0 |
| rows: 8 abutted rows, mux2_1 between 34 neighbour types, N/FS, flipped/unflipped, mux2_1 over mux2_1 across rows | 0 | 0 | 0 | 0 | 0 |
| pairs: mux2_1\|mux2_1 in all 4 orientation pairs, N and FS rows | 0 | 0 | 0 | 0 | 0 |
| routed test block, 80 mux2_1 | 0 (in-flow) | 0 | 0 | 0 | 0 |
| **chip x0 (117 mux2_1)** | **0 (in-flow)** | **0** | **0** | **0** | **0** |
| chip h2 (reference) | 0 (in-flow) | 0 | 0 | 0 | 0 |
| positive control: contact with 0.005 µm Metal1 overlap | CO.6, M1.3 | CO.6b, M1.3 | | CO.6b, M1.3 | |
| positive control: Metal1 0.10 µm spacing | M1.2a | M1.2a | | M1.2a | |

Notes:
- **DF.13_MV/DF.14_MV** are the maximum tap distances. A cell drawn without taps trips them, and every control
  cell (mux2_2, addf_1, oai33_1/2) does the same. They vanish once taps are present.
- **Routed test block** (`drc/tblock/`): 64 hand-instantiated plus 16 synthesized mux2_1 under real routing, in all
  4 orientations (30 N, 26 FS, 14 S, 10 FN).
  - Abutting neighbours: fill, fillcap, filltie, xor2, dffrnq, dlyb, mux2, clkinv, nand2, clkbuf, nor2, nand3,
    aoi21, xnor2.
  - Signoff: Magic 0, LVS clean, antenna 0.
- **Chip x0**: 117 mux2_1 in all 4 orientations, next to 23 neighbour families (`drc/chip_x0_mux2_1_neighbours.txt`).
- **Not used by the TT gf180mcuD flow**: the LibreLane KLayout.DRC step (it is skipped because `KLAYOUT_DRC_RUNSET`
  is unset for gf180mcuD) and the TT precheck's Magic DRC (it is for sky130A only). The checks that apply are the
  in-flow Magic DRC and the precheck's KLayout deck, and both are clean.

**Finding:** mux2_1 is DRC-clean on every deck that the TT flow signs off with: alone, abutted, flipped, routed
and in the chip. The exclusion is a 2022 workaround for a Magic rule that has since been fixed.

### Measured on the chip

- Allowing mux2_1 means a design-level `PNR_EXCLUDED_CELL_FILE` that keeps only `oai33_2`. That one setting covers
  synthesis and PnR.
- x0's synthesis netlist changes from `a339bf99…` to `99daa702…`.

## Experiment 3: combination

| Run | Configuration | Area | Δ h2 | Slew/cap/fo | Setup WNS | Hold WNS (ff −40 °C) |
|---|---|---:|---:|---|---:|---:|
| x0_mux21 / **x0_full** | h2 + mux2_1 | **44,911.6** | **−564.2** | 242/1/0 | +43.16 | +0.007 |
| x2_mux21_no4 | x0 + m2 (no drive-4) | 44,924.8 | −551.0 | 223/1/0 | +42.48 | +0.001 |
| x4_mux21_root12 | x0 + clkbuf_12 CTS root | 44,990.6 | −485.2 | 214/1/0 | +42.59 | +0.015 |
| x3_mux21_root16 | x0 + clkbuf_16 CTS root (h3's knob) | 45,069.7 | −406.1 | 222/1/0 | +42.90 | +0.036 |

- mux2_1 is the only winner. Adding m2 (x2) costs 13.2 µm² more than x0 and leaves hold at +0.001 ns.
- The final configuration is therefore **x0**.
- x3 is the hold-safer alternative (`alt_holdsafe_config.patch`). It has only been screened to step 55 and needs a
  signoff harden before use.
- x3 and x4 change only the 3 CTS root/trunk buffers. Logic and repair are identical to x0.

### Attribution of x0's −564.2 µm²

| Part | Δ µm² | By master |
|---|---:|---|
| Synthesis | **−311.7** | −67 mux2_2 (−2,206.2) and +119 mux2_1 (+3,396.0). ABC builds 52 more muxes from the cheaper mux2_1 and drops 49 oai21_1, 31 nand2_1, 13 aoi21_1, 5 nor3_1, 5 clkinv_1 and others (−1,501.5 net). Cells go from 1,434 to 1,380. |
| Resizing | +24.1 | 49 resizes (h2: 47), including 2 mux2_1 → mux2_2 (+8.8) |
| Repair buffers | −184.4 | 27 (18 buf_3, 8 buf_4, clkbuf_4), against 33 (21 buf_3, 7 buf_4, buf_8, clkbuf_3, 3 clkbuf_4) |
| CTS | −92.2 | 17 clkbuf_4 + 3 clkbuf_8 + 2 clkinv_4 + inv_4, against 19 clkbuf_4 + 3 clkbuf_8 + 7 clkinv_1 + clkinv_4 + inv_2 (fewer dummy loads) |
| **Total** | **−564.2** | by class: logic −232.7, repair −184.4, clock −92.1, inverter −39.5, flop −15.4 |

- The gain is above the 400 µm² bar and is traced by class and master.
- It was **reproduced bit-identically** by the full harden. The step-55 screen and the full harden produced the
  same files:
  - synthesis `99daa702…`;
  - post-CTS `291a0d8a…`;
  - routed netlist `78623609…` and DEF `4b07f63c…`;
  - SPEF, equal apart from `*DATE`.
- m0_ctrl_s55 likewise reproduces h2's signoff exactly.
- The synthesis part is a property of the library and is deterministic. The repair and CTS part (−276.6) comes
  from the new placement, so it can move by about the harden noise (75 µm²) on any RTL change.

## Risks

1. **Hold margin at ff −40 °C is thin: +0.007 ns** (h2 +0.058).
   - The check includes the 0.25 ns clock uncertainty.
   - The worst path is the flop-to-flop shift `core.mac.ring[124]` (`_2341_` → `_2321_`). Its launch and capture
     leaves (`clkbuf_leaf_13` and `_14`) differ by 0.21 ns.
   - Post-CTS hold repair estimated +0.099 ns against its 0.1 ns margin and inserted nothing (RSZ-0064).
   - The TT flow has no post-GRT hold repair.
   - Any RTL or netlist change can push this path negative. Re-check hold at all 9 corners after every change.
   - If more margin is wanted, use x3: −406 µm², +0.036 ns.
2. **The PDK file is overridden.**
   - `src/pnr_exclude_md.cells` replaces the PDK's `drc_exclude.cells` entirely.
   - If a future PDK adds an entry there, the project will not pick it up. Re-sync the file on any PDK bump.
   - Upstream still lists mux2_1. Nobody has re-qualified it upstream; the evidence here is project-local.
3. **TT precheck tooling.**
   - The TT precheck uses PDK e8daeda7 and KLayout 0.30.4 (`tt/precheck/tool-versions.json`; pip ≥ 0.30.8). I ran
     the same deck file and options with KLayout 0.30.7 (the image's).
   - The full `precheck.py` was not run, because gdstk is not installed on the host or in the image. Its
     layout-level checks were re-implemented (`scripts/drc/tt_layout_checks.py`; negative control fails) and pass.
   - The DEF boundary, pin, power-pin and Verilog checks were not run. They do not depend on which cells are placed.
4. **KLayout DRC runs only at precheck.** The TT harden itself guards with Magic only (KLayout.DRC is skipped for
   gf180mcuD), which is the same as for h2.
5. **Run time under load.** Screens took about 1 minute on an idle machine, but 12–34 minutes while other agents'
   containers ran.

## Not pursued

- **oai33_2.** It is not a minimum-drive cell (oai33_1 exists and synthesis uses it). It also looks clean in
  isolation (Magic 0; KLayout DF.13/14 context items only), but it was not chip-tested.
- **Re-allowing buf_1/buf_2/clkbuf_1/clkbuf_2/dly\*.** h2 excludes them with measured evidence
  (`../EXPERIMENTS.md`), and the brief said to keep buffers as they are.
- **`-pre_placement`, `-match_cell_footprint`, `-sizing_area_limit`.** LibreLane 3.0.14 does not expose them.

## Files

- `recommended_config.patch`: x0. It is a delta on top of `../recommended_config.patch` (h2) and adds
  `src/pnr_exclude_md.cells`.
  - Not applied.
  - `git apply` of h2's patch and then this one passes.
  - The result is semantically equal to the x0_full config.
- `alt_holdsafe_config.patch`: x3 (the same plus `CTS_ROOT_BUFFER` clkbuf_16), also relative to h2; equal to
  the x3 config.
- `results.json`: every run (area by class and census group, per-corner WS, violations, power, signoff, synthesis,
  post-repair and post-CTS hashes, resize/insert attribution, overrides, deltas against h2) plus `_mux2_1_drc`
  and `_mux2_1_test_block`.
- `overrides/*.json` (made by `scripts/make_overrides.py`).
- `runs/full/x0_full/`: config, metrics, signoff reports (Magic DRC, LVS, manufacturability), final and post-CTS
  netlists (gz), STA checks, attribution and SHA256SUMS.
- `runs/partial/<tag>/`: config, post-CTS netlist (gz), repair/CTS logs (gz), census, attribution and SHA256SUMS.
  The synthesis netlist is kept only where it differs from h2's.
- `drc/`:
  - `drc_summary.json` (every report above, with GDS hashes);
  - `evidence.tar.gz` (test GDS, all lyrdb, logs and Magic reports);
  - `tblock/` (test-block sources, run script, metrics);
  - `tt_layout_checks.txt`, `*_neighbours.txt`, `large_gds.sha256`.
- `scripts/`:
  - `run_md.sh`, `batch.sh`, `save_evidence.sh`, `collect_md.py`, `upsize_diff.py`, `families.py`,
    `make_overrides.py`;
  - `drc/`: test generators, Magic and KLayout wrappers, the TT-deck Docker wrapper, `collect_drc.py`,
    `neighbours.py`, `tt_layout_checks.py`.
