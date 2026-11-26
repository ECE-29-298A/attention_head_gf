# ripple_add Phase 4: physical implementation (N=22, N=12 hardened blocks)

The paths in this file are relative to `pd_flow/modules/ripple_add/impl/` unless stated otherwise.
Nothing under `src/`, `test/`, the PDK or the reference was edited, and nothing was committed.
`src/ripple_add.v` (the golden RTL) is still what ships. These blocks are standalone evidence for the
approved placement plan, `../layout_plan/PLAN.md`. The chip integration evidence is the existing run
`../layout_plan/chip_runs/fixed_a3`, which is not shipped (D3).

Result labels follow AGENT_CONTEXT: `proven`, `pass-exhaustive`, `pass-sampled`, `pass-static`,
`bounded-pass`, `failed`, and `GAP` for anything not done or not closed.

## 1. Methodology

| Item | How |
|---|---|
| Netlist | Approved `../layout_plan/out/ripple_add_n{22,12}.v`. It has 21 or 11 `addf_1` plus one `xor3_1`, with A3 = c[N-1]. |
| Placement | `MACRO_PLACEMENT_CFG` from the approved `block_n*.cfg` gives FIXED std cells at the plan coordinates, one row per bit. The flow places no logic cells. |
| Routing | OpenROAD global and detailed routing, automatic, on Metal2 to Metal4. There are no hand routes, no suppressed violations, and no deck edits (D4). |
| Pins | `FP_DEF_TEMPLATE` (`scripts/make_pin_template.py`) aligns pins to rows on the plan sides: W has a[i] and s[i], E has b[i], S has cin. |
| Flow | LibreLane 3.0.14 in Docker, gf180mcuD, run tag `impl`. The space-free work dir is `/Users/samuelzhang/ttharden/ra_impl_n{N}`. Results are copied back to `n{N}/run/`. |
| Config deltas from the plan template | Recorded in config `//phase4_changes`: VPWR/VGND pins; TT gf180 corner set; IO pin length 2; `SYNTH_ELABORATE_ONLY=false` (the plan's `assign c[0]=cin` fails the assign-statement checker; P4 proves the instances are unchanged); `PDN_VOFFSET 7.91` (16.32 fails PDN-0185 in a 20.72 µm core, so this is a **PDN stripe deviation from the plan**); `RUN_KLAYOUT_XOR`. |
| Superseded attempt | `n22/attempts/r1_centered_pins/`: CustomIOPlacement centred the pins, which raised wirelength from 484 to 944 µm. It was replaced by the DEF template. |
| Block checks | `scripts/check_block.py` writes `n{N}/check_block.json`, ALL_PASS for both N. It checks: P1, FIXED coordinates exact in every step DEF from step 17 on; P2, no overlaps and endcaps at both ends of every row; P3, pin side and row; P4, nl/pnl logic identical to the approved netlist; P5, routing only on M2–M4 and every net routed; P6, sizes. |

**Sizes**

| N | Die (µm) | Core (µm) | Logic bounding box | Cell area | Bbox utilisation |
|---|---|---|---|---|---|
| 22 | 27.44 × 94.08 = 2581.56 µm² | 20.72 × 86.24 = 1786.89 µm² | 18.48 × 86.24 = **1593.72 µm²** | 1571.76 µm² | 98.6 % |
| 12 | 27.44 × 54.88 = 1505.91 µm² | 20.72 × 47.04 = 974.67 µm² | 18.48 × 47.04 = **869.30 µm²** | 847.35 µm² | 97.5 % |

The Liberty `area` value is the core area, not the die area.

## 2. PDK and rules used

- **PDK and devices:** gf180mcuD, ciel version `54435919abff…`. The cells are `gf180mcu_fd_sc_mcu7t5v0` (7-track, 5 V devices `nfet_05v0`/`pfet_05v0`) run at 3.3 V.
- **KLayout DRC:** KLayout 0.30.14, PDK `libs.tech/klayout/tech/drc/gf180mcu.drc`, variant D switches `metal_top=11K metal_level=5LM mim_option=B feol=beol=offgrid=conn_drc=true run_mode=deep`. The separate decks `rule_decks/antenna.drc` and `density.drc` were also run.
- **KLayout LVS:** `libs.tech/klayout/tech/lvs/gf180mcu.lvs`, deep mode, `lvs_sub=VSUB`, against a PDK-CDL schematic.
- **Flow checks:** LibreLane's Magic DRC, KLayout XOR, Netgen LVS and OpenROAD antenna checks. Magic uses the PDK `gf180mcuD.magicrc`.
- **ngspice:** ngspice-47 with PDK `design.ngspice` and `sm141064.ngspice` sections `typical`, `ss` and `ff`.

## 3. DRC

| Check | N=22 | N=12 | Log |
|---|---|---|---|
| OpenROAD route DRC, Magic DRC, KLayout XOR, illegal overlap | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | `n*/run/final/metrics.json`, `n*/run/steps/` |
| KLayout main deck (651 rules) | **0** | **0** | `n22/drc/n22_main.lyrdb`, `n12/drc/n12_main.lyrdb` |
| DF.13_MV / DF.14_MV | **0 / 0** | **0 / 0** | in `n*/drc/n*_summary.json` |
| Same deck on the KLayout-streamed GDS | 0, DF.13/14 = 0 | – | `n22/drc/n22_klayoutgds_*` |
| KLayout antenna deck | 0 | 0 | `n*/drc/n*_antenna.lyrdb` |
| KLayout density deck | 7 (DCF.1b, M1.4, M2.4, M3.4, M4.4, M5.4, MT.3) | 7 (same rules) | `n*/drc/n*_density.lyrdb` |

**Positive control.** `drc_reference/` runs the same deck on a bare PDK `addf_1` and a bare `xor3_1`. Each gives 4 violations: 2 DF.13_MV and 2 DF.14_MV, because a cell alone has no tap. A bare `endcap` gives 0. So the deck does detect DF.13/14, and the block's endcaps provide the taps.

**Density classification.** The density rules are minimum and maximum coverage rules over the whole die. They need dummy fill, which a 27 µm block cannot meet on its own. This is not a waiver: the chip-context check below shows the same family on both the baseline chip and fixed_a3. In fixed_a3 the same rule family appears (M2.4–M5.4, MT.3: 5 items), and the unmodified baseline chip (`chip_context/drc_base/base_summary.json`) has the identical 5. So the density items already exist at chip level and are not caused by the block. In fixed_a3 the main deck gives **0**, DF.13/14 give **0**, and antenna gives **0** (`chip_context/drc_fixed_a3/fixed_a3_summary.json`). Tiny Tapeout fills at shuttle assembly, but that fill was not run here (**GAP**: the block is not density-clean standalone).

## 4. LVS

| Check | N=22 | N=12 | Evidence |
|---|---|---|---|
| Netgen (flow, cell-level, black-box cells, pin names enforced) | **Circuits match uniquely** | **Circuits match uniquely** | `n*/lvs/flow_netgen_lvs.rpt` |
| KLayout transistor-level vs the PDK CDL (612 or 332 devices) | **Congratulations! Netlists match** | **Netlists match** | `n*/lvs/klvs_n*.log`, `.lvsdb`, `_xref.json` |

- **CDL construction.** `scripts/make_cdl.py` builds the CDL from the pnl with the PDK `.cdl` cells. VPW goes to a VSUB port because the deck treats the substrate as a separate global net. Device-less endcap and fill cells are omitted.
- **Netgen controls.** Positive control: matches. Negative control with s[3] and s[4] swapped: fails with "Top level cell failed pin matching", as expected.
- **KLayout controls.** With a[4]'s input tied to a[3], it fails ("Netlists don't match"), as expected. With s[3] and s[4] swapped, it still matches. KLayout LVS is topological and does not enforce port names. Netgen covers port names, so the pair of tools is complete. On its own, KLayout LVS is not a pin-name check (**known limitation**).
- **macOS shim.** The deck calls Linux `pmap`. `scripts/shim/pmap` is a host shim used only for memory logging; it does not change rules.

## 5. ERC

| Item | Result |
|---|---|
| Antenna | OpenROAD `route__antenna_violation__count` is 0, antenna nets 0, and no diodes were inserted. KLayout antenna deck: 0 for both N and for the chip. |
| Well and tap | No filltie was inserted, because a row is 18.5 µm and the tap distance is 100 µm. Every row has endcaps at both ends, which contain the taps (P2). KLayout DF.13_MV/DF.14_MV are 0. The positive control (bare cell gives 2 + 2) shows the rule fires. |
| Floating inputs | `design__disconnected_pin__count` is 0. Netgen matches with every cell pin connected. The layout-extracted Verilog (§8) has every cell input on a port or on the single-driver carry net. The KLayout LVS netlist has no unconnected gate nets. |
| Power grid | `design__power_grid_violation__count` is 0. Worst IR drop is 6.1 µV. |

## 6. Extraction

- **OpenRCX:** SPEF at min, nom and max: `n*/run/final/spef/`.
- **Magic transistor level:** `scripts/magic_extract.sh N` gives `n*/pex/ripple_add_n*_pex.spice`.
  - Settings: `extract do capacitance coupling adjust`, `no resistance`, `ext2spice cthresh 0`, flat.
  - N=22: 612 devices, 2485 C elements, total C 605 fF.
  - N=12: 332 devices, 1382 C.
  - The 1376 Magic warnings are all "node labels should be inside overlap area" (naming only; LVS matches).
  - **GAP:** no wire resistance in the PEX. Routes are under 30 µm, and OpenRCX R is in the SPEF.

## 7. Post-layout characterisation

### Test conditions

- **Boundary:** every input is driven by an ideal source with a 0.375 ns 0–100 % ramp, which equals a Liberty slew of 0.30 ns (30–70 %, derate 0.5). Every s[i] has a **20 fF** load.
- **SPICE:** the Magic PEX netlist under ngspice-47 (`scripts/spice_char.py`). Results are in `n22/spice/<corner>_<test>.json` and logs in `.log` files beside the `.cir` decks.
- **STA:** OpenSTA with the nom SPEF and the PDK Liberty (`scripts/sta_char.sh`), giving `n*/sta/sta_summary.json`. SPICE and STA numbers are reported separately below and never mixed.

### Functional tests (SPICE, N=22)

19 vectors at each of tt, ss and ff, each **PASS 19/19** (`pass-sampled`):

- full ripple with cin=1;
- cin=1 with a = all ones;
- the subtract form a + ~b + 1 for several pairs;
- random cases;
- each compared against the golden model.

The worst logic-level error was 0 % of VDD. N=12 at tt also passed 19/19 (`n12/spice/tt_func.json`).

### Characterisation table, N=22

Delays are worst-case sensitised arcs a[0]/b[0]/cin → s[21], 50 %–50 %.

| | tt 25 °C 3.3 V | ss 125 °C 3.0 V | ff −40 °C 3.6 V |
|---|---|---|---|
| **SPICE (PEX)** worst delay (b[0]↓ → s21) | **22.11 ns** | **44.04 ns** | **12.66 ns** |
| SPICE cin↑ / cin↓ → s21 | 18.52 / 22.02 | 36.16 / 43.86 | 10.91 / 12.61 |
| SPICE s21 slew (Liberty-equivalent 30–70/0.5), output rise / fall | 0.53 / 1.15 ns | 1.00 / 2.24 | 0.32 / 0.66 |
| SPICE energy per op, mean (min–max) | 6.42 (3.25–9.48) pJ | 5.17 (2.63–7.65) | 8.07 (4.06–11.87) |
| SPICE energy, full ripple cin↑ / cin↓ | 5.74 / 10.47 pJ | 4.63 / 8.47 | 7.16 / 12.95 |
| SPICE leakage, mean / max over 5 states | 0.073 / 0.084 nW | 0.93 / 1.42 nW | 0.060 / 0.081 nW |
| SPICE input cap a / b / cin, mean | 11.5 / 10.5 / 10.4–10.7 fF | 11.2 / 10.2 / 10.2–10.5 | 12.0 / 10.9 / 10.7–11.0 |
| **STA+SPEF** sensitised cin↑ / cin↓ → s21 | 15.44 / 18.60 ns | 31.57 / 38.70 | 8.80 / 10.32 |
| STA+SPEF unsensitised worst | 19.57 ns | 40.76 | 10.81 |
| STA Liberty-only worst (no wire RC) | 19.28 ns | 40.13 | 10.66 |
| **Block Liberty model** worst | 19.97 ns | 41.51 | 11.04 |
| STA s21 slew, sensitised cin↓ | 1.15 ns | 2.25 | 0.64 |
| Liberty pin cap a / b / cin (a[21] / b[21] go to xor3) | 12.2 (7.1) / 11.6 (5.4) / 9.8 fF | 12.3 / 11.8 / 10.2 | 12.4 / 11.8 / 9.7 |
| STA vectorless power (estimate only) | 116.7 µW | 96.7 µW | 141.7 µW |
| STA leakage | 3.6 nW | 28.4 nW | 4.3 nW |
| Max slew / cap violations at 20 fF | 0 | 0 | 0 |

**Notes on the table**

- **Activity.** Each SPICE operation draws a, b and cin uniformly at random (seed 7), so each bit toggles with probability 0.5, about 21.9 input toggles per operation. There are 40 operations in one period each (tt 40 ns, ss 90 ns, ff 30 ns). The energy is the VDD charge × VDD, including the 20 fF output loads and leakage over the window. It excludes input-pin charge, which the ideal sources supply. The STA power uses activity 0.5 per 100 ns, a different definition, so the two are not directly comparable.
- **Leakage.** This is the `.op` current, rerun with `gmin=1e-15 abstol=1e-18`. At ngspice's default gmin of 1e-12 S, the gmin current alone was about 0.7 nA, 25× the real value. The superseded results are in `n22/spice/superseded_gmin_default/`. At 1e-18 the values change by less than 6 %. Liberty leakage is 10–50× higher than SPICE. Both are negligible (under 30 nW), but they **disagree** (GAP, no impact).
- **Input capacitance.** This is the charge drawn during the input ramp, divided by VDD, with the other inputs at 0. SPICE and Liberty+SPEF agree within about 10 %.

### N=12 (STA, plus SPICE at tt)

| | tt 25 °C 3.3 V | ss 125 °C 3.0 V | ff −40 °C 3.6 V |
|---|---|---|---|
| SPICE worst delay | 11.95 ns | – | – |
| STA+SPEF worst | 10.70 ns | 22.23 | 5.93 |
| Block Liberty worst | 11.10 ns | 22.98 | 6.16 |

The N=12 SPICE run at ss/ff, and the energy, leakage and input-cap SPICE runs for N=12, were not done (GAP, optional). `n12/sta/sta_summary.json` holds the full STA numbers.

### SPICE against STA (Liberty against SPICE delay)

`views/views_n22.json` V4 gives these ratios:

| Ratio | tt | ss | ff | N=12 tt |
|---|---|---|---|---|
| SPICE-PEX / block Liberty | 1.107 | 1.061 | 1.146 | 1.077 |
| SPICE-PEX / STA sensitised | 1.18 | 1.13 | 1.22 | 1.17 |
| Block Liberty / STA+SPEF | 1.02 | 1.02 | 1.02 | 1.04 |

- **Block Liberty is slightly pessimistic.** It is 2–4 % above STA+SPEF. `write_timing_model` merges both input edges into one non-unate value.
- **SPICE is 6–15 % slower than the block Liberty**, and 13–22 % slower than sensitised STA. This is a **real, explained disagreement, not a pass.**
  - Single-cell calibration (`spice_calibration/README.txt`) at the same boundary, for addf_1 CI→CO at tt (rise / fall):
    - SPICE on the PDK schematic, no C: 0.45 / 0.52 ns;
    - PDK Liberty: 0.70 / 0.83 ns;
    - SPICE on the Magic PEX of the cell alone: 0.81 / 0.99 ns.
  - So the ratio of 1.15–1.19 already exists **inside one PDK cell**. The routing adds only 2–4 % (SPEF against Liberty-only).
  - The pre-layout schematic SPICE of the whole block is 7.5 / 9.0 ns (`n22/spice_schematic/tt_delay.json`), a lower bound.
  - Conclusion: Magic's intra-cell C extraction is heavier than the parasitics the PDK used to build its Liberty. Which one is right is not settled here (**GAP**).
- **Chip impact.** fixed_a3 closes setup with WNS 25.26 ns at max_ss (100 ns clock). That is far more than a 15 % increase on the adder's 44 ns ss path (about 6.6 ns).

### Slew at the flow's default load

The flow reports 44 (N=22) and 24 (N=12) max-slew violations. These are measured with LibreLane's default `OUTPUT_CAP_LOAD` of 72.91 fF on every output against a 3 ns limit. For example, at ss s[21] is 7.2 ns and addf S is about 3.5 ns. At the 20 fF boundary there are **0** violations at every corner.

Chip-context check (`chip_context/chip_slew_adder.txt`, fixed_a3 step 55, all 9 corners):

- **No ripple_add output pin (S/CO/Z) violates in any corner.**
- Two `l_adder` B *inputs* (bitslice 3 and 7) are at 3.12 and 3.03 ns at max_ss. They are driven by chip logic outside the block.
- The chip's 399 slew violations are pre-existing: the baseline chip has 381.

So the block's slew violations come from the default 72.91 fF boundary load and do not occur in context. They are not waived.

## 8. Views and consistency

`scripts/check_views.py N` writes `views/views_n{N}.json`, which has the sha256 of every view. **STRUCTURAL_PASS** for both N:

- **V1 pins:** 22 views carry the same port set and directions. They are the LEF, the GDS top labels, the DEF, nl, pnl, the layout-extracted Verilog, the behavioural Verilog, the CDL, the flow-extracted SPICE, the PEX, 9 flow Liberty files and 3 block-model Liberty files.
- **V2 sizes:** the LEF SIZE, DEF DIEAREA and GDS bbox are equal (27.44 × 94.08 and 27.44 × 54.88).
- **V3 pin rectangles:** all 67 (or 37) LEF pin rectangles equal the DEF pin rectangles.
- **V4 delay:** the ratios in §7.

| View (N=22) | Path | sha256 (first 16) |
|---|---|---|
| GDS (Magic) | `n22/run/final/gds/ripple_add.gds` | fa6932b9fb2b2f4f |
| GDS (KLayout stream) | `n22/run/final/klayout_gds/ripple_add.klayout.gds` | d37e67861ac0e7f4 |
| LEF | `n22/run/final/lef/ripple_add.lef` | badb5eacc1405ca3 |
| DEF | `n22/run/final/def/ripple_add.def` | 1b57334b8078f480 |
| Gate Verilog nl / pnl | `n22/run/final/{nl,pnl}/` | 09c2810179b1fa0a / 9c38dde3d7484ee7 |
| Layout-extracted Verilog | `contract/ripple_add_n22_extracted.v` | 77a6287998c28589 |
| Behavioural Verilog | `views/ripple_add_n22_behav.v` | e56dd0abba7c340a |
| CDL (PDK cells) / SPICE schematic | `n22/lvs/ripple_add_n22.{cdl,spice}` | 0aa849268cad3428 / fbd31047c0386c01 |
| Magic PEX SPICE | `n22/pex/ripple_add_n22_pex.spice` | b0c93fdeccce9701 |
| SPEF nom | `n22/run/final/spef/nom/ripple_add.nom.spef` | 7507cb6775942f60 |
| Liberty flow tt / ss / ff (nom) | `n22/run/final/lib/nom_*/` | de0dd35694d711b8 / 847037aa0544f918 / 2120418142d7301f |
| Liberty block model tt / ss / ff | `n22/sta/ripple_add__*.lib` | 1a44c89b3baa5219 / 7b34d3ff0b914a5e / fd55b30628bbd720 |

`views/views_n12.json` has the N=12 hashes, for example GDS b8665a56f557362d and LEF b7d8c4525f002220.

### Frozen contract on the views

The contract was run from `../verif/run_all.sh`. `CONTRACT.sha256` re-verified 17/17 files OK.

| DUT | Result | Path |
|---|---|---|
| Layout-extracted N=22 | all_ok, 10/10: fv_prove `proven`, fv_pdr `proven`, 216 556 vectors + 50 M random `pass-sampled`, cover 16/16, sanity mutant `failed-as-expected` | `contract/n22_extracted/` |
| Layout-extracted N=12 | all_ok, 11/11, including **exhaustive 2^25 `pass-exhaustive`** and proofs | `contract/n12_extracted/` |
| Behavioural view, N=22 / N=12 | all_ok, 10/10 and 11/11 | `contract/n{22,12}_behav/` |

The extracted netlist is built by `scripts/extracted_to_verilog.py` from Magic's cell-level extraction of the **final GDS** (`final/spice/ripple_add.spice`, the netlist that Netgen matched). So the contract sees the layout connectivity, not the netlist that was fed into the flow.

## 9. Integration (fixed_a3, not shipped)

### Netlist check

`scripts/check_chip_integration.py` writes `integration/chip_netlist_check.json`: **ALL_PASS**.

- **I1:** the final chip nl and pnl instantiate exactly `core.mac.adder.bitslice[0..20].u_fa` (addf_1) plus `u_msb_x3` (xor3_1), and the same for `core.mac.l_adder` with N=12. The carry chain runs CO(i) → CI(i+1) and CO(N−2) → A3. Every carry net has one driver and one load: no buffers, no resizing.
- **I2:** the synthesis netlist (step 06) is the same, so Yosys and ABC did not remap the cells.
- **I3:** all 34 cells are FIXED at their `ra_fixed.cfg` coordinate and orientation in the final DEF.
- The only extra cells in that namespace are 5 `tiel` cells under `l_adder`. They come from the chip's constant inputs, not from the adder.

### Gate-level top test

`test/top/run.py --netlist … --cell-models …` was run unchanged.

| Netlist / models | Result | Log |
|---|---|---|
| fixed_a3 pnl, PDK functional models as-is | FAIL at 31 ns, `Logic('X')` on uio_out[3] (3 tests) | `integration/superseded/gl_top_fixed_a3_pnl_pdkmodels.log` |
| fixed_a3 pnl, flops initialised to 0 | **PASS 3, SKIP 1** | `integration/gl_top_fixed_a3_pnl_init0_pwr.log` |
| fixed_a3 pnl, flops initialised at random | **PASS 3, SKIP 1** | `integration/gl_top_fixed_a3_pnl_initrand_pwr.log` |
| fixed_a3 nl, flops initialised to 0 | **PASS 3, SKIP 1** | `integration/gl_top_fixed_a3_nl_init0_nopwr.log` |
| Negative control: nl with adder s[3]/s[4] swapped | **FAIL as expected**, e.g. `hardware=[-2048,-17,…] Python=[-2048,-16,…]` | `integration/negative_control/` |

- **The skipped test.** `real_smollm_head` is skipped by the test itself, `skip=not SMOLLM.exists()`, because the SmolLM data file is not present.
- **Root cause of the X.** All 329 chip flops are `dffq` cells without reset. The datapath has no reset by design.
  - The PDK UDP flop starts at X.
  - Cocotb starts `clk` high at t = 0, so Icarus sees an X→1 "posedge" at t = 0, before the combinational logic settles, and the flops capture X.
  - Hold-muxed datapath flops then keep that X. Gate-level X-pessimism carries it to the SCK pin.
  - `integration/xdebug/` holds the waveform localisation: `scripts/run_gl_debug.py`, a copy of run.py's flow with VCD output.
  - Initialising the flops alone is not enough: with init 0 the test still failed at 1351 ns because of the t = 0 edge.
- **Fix used.** `scripts/make_gl_models.py` takes the PDK functional models, copied with only `dffq_1/2/4` replaced. The replacements have the same ports and function, Q <= D on a real CLK rise. Their state is initialised to 0 or `$urandom`, and they ignore the t = 0 pseudo-edge.
  - Real flops power up at 0 or 1, never X. The random-init pass shows the design does not depend on any particular power-up value.
  - Alternatives would be a 2-state simulator (Verilator) or a reset on the datapath flops. The latter is an RTL change and out of scope.

## 10. Reproduction

`scripts/reproduce_all.sh` runs every step in order. Its key commands:

```
scripts/run_block.sh 22 ; scripts/run_block.sh 12          # Docker harden, one at a time
python3 scripts/check_block.py N n<N>/run n<N>/check_block.json
scripts/run_klayout_drc.sh n<N>/run/final/gds/ripple_add.gds ripple_add n<N>/drc n<N>
python3 scripts/make_cdl.py n<N>/run/final/pnl/ripple_add.pnl.v n<N>/lvs/ripple_add_n<N>.cdl cdl --sub VSUB --omit-empty
RUN_MODE=deep scripts/run_klayout_lvs.sh n<N>/run/final/gds/ripple_add.gds n<N>/lvs/ripple_add_n<N>.cdl n<N>/lvs klvs_n<N>
scripts/netgen_lvs.sh <layout.spice> <netlist.v> <outdir> <tag>
scripts/magic_extract.sh N ; scripts/sta_char.sh N
python3 scripts/spice_char.py 22 {tt|ss|ff} n22/spice [func delay energy leak cin] [--netlist FILE]
python3 scripts/extracted_to_verilog.py n<N>/run/final/spice/ripple_add.spice N contract/ripple_add_n<N>_extracted.v
../verif/run_all.sh --rtl contract/ripple_add_n<N>_extracted.v --gate N --out contract/n<N>_extracted
python3 scripts/check_views.py N views/views_n<N>.json
python3 scripts/check_chip_integration.py integration/chip_netlist_check.json
python3 scripts/make_gl_models.py integration/cell_models_init0_pwr.v zero --power-pins
python3 test/top/run.py --netlist <fixed_a3 pnl> --cell-models <models>     # from the repo root
```

The Docker work directories are space-free: `/Users/samuelzhang/ttharden/ra_impl_*`. ngspice runs with cwd set to the output directory and a relative include, because the project path contains a space.

## 11. Gaps (not passes)

1. **SPICE against Liberty delay:** SPICE (Magic PEX) is 6–15 % slower than the block Liberty. The cause is localised to intra-cell extraction by single-cell calibration, but which value is right is not settled. Chip setup margin (25 ns at ss) covers it.
2. **Density:** 7 standalone density-rule items, which need fill. The same family appears at chip level, also on the baseline chip. Shuttle-level fill was not run.
3. **KLayout LVS** does not enforce port names; it is topological. Netgen covers this, with a negative control that fails as it should.
4. **No wire R in the Magic PEX**, only C and coupling. OpenRCX SPEF includes R.
5. **PDN stripe offset** is 7.91 µm instead of the plan's 16.32, because of PDN-0185 in a 20.72 µm core. This applies to the standalone block only.
6. **Block Liberty** from `write_timing_model` merges the two input edges, so it is 2–4 % pessimistic.
7. **Leakage:** SPICE and Liberty differ by 10–50×. Both are negligible.
8. **N=12 SPICE** only at tt (functional and delay); no ss/ff, energy, leakage or input cap.
9. **The gate-level top test needs the initialised-flop models** (§9). With the stock PDK UDP models it fails on every netlist, including the baseline chip, because of the X at t = 0.
10. **Flow slew violations at the default 72.91 fF load** (44 and 24) remain in the standalone metrics. They are 0 at 20 fF and 0 on block outputs in chip context. They are classified, not waived.
