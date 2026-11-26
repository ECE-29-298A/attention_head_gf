# ripple_add Phase 3: independent notes (Agent 5, written before reading the plan)

Derived directly from the PDK files, the chip config and a baseline run tree. Parser:
`leftab.py` in this directory (tokenizer, not block regex; 229 macros parsed, all non-empty).

## Sources (hashes, first 16 hex of SHA-256)

| File | Hash |
|---|---|
| `libs.ref/gf180mcu_fd_sc_mcu7t5v0/lef/gf180mcu_fd_sc_mcu7t5v0.lef` | `47dadf84c21b20f5` |
| `libs.ref/gf180mcu_fd_sc_mcu7t5v0/techlef/gf180mcu_fd_sc_mcu7t5v0__nom.tlef` | `1e15a88b384e015e` |
| `libs.ref/.../lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib` | `f9dee07cf1583249` |
| `libs.ref/.../gds/gf180mcu_fd_sc_mcu7t5v0.gds` | `efa44f076c96508a` |

PDK: `$PDKV` = ciel gf180mcu `54435919…`, variant gf180mcuD. Chip config: `ttharden/attention_head_gf/src/config_merged.json`.
Baseline run tree used for floorplan facts: `/Users/samuelzhang/ttharden/ra_base/runs/wokwi` (`resolved.json`, `final/def`).

## Site, rows, grid

- Site `GF018hv5v_mcu_sc7`: **0.56 × 3.92 µm**, `SYMMETRY X Y`, CLASS core. DEF units 2000/µm, manufacturing grid 0.005 µm.
- All 229 masters are 3.92 µm tall (single height) and declare `SYMMETRY X Y`, so N, FN, S and FS are all
  allowed by the LEF. In practice the row orientation (N or FS) fixes the vertical flip. Legal cell orientations
  are N/FN on N rows and FS/S on FS rows.
- Die 346.64 × 160.72 µm (`DIE_AREA`). Margins: LEFT/RIGHT_MARGIN_MULT 6 sites = 3.36 µm, TOP/BOTTOM 1 row = 3.92 µm.
  Core x = 3.36 … 343.28 (339.92 µm = **607 sites**), y = 3.92 … 156.80 (152.88 µm = **39 rows**). 607 × 39 × 2.1952 µm² = 51,967 µm² core.
- Rows (DEF): `ROW_r` at x = 6720 DBU (3.36 µm), y = 7840 + 7840·r DBU, **N for even r, FS for odd r**, 607 sites, step 1120 DBU.
  Row 0 (bottom) is N. A legal anchor is x = 3.36 + 0.56·k, y = 3.92 + 3.92·r.

## Routing layers and tracks (tech LEF and `tracks.info`)

| Layer | Dir | Pitch | Offset (tracks.info) | Width / space | Min area |
|---|---|---:|---:|---|---:|
| Metal1 | H | 0.56 | 0.28 | 0.23 / 0.23 | 0.1444 |
| Metal2 | V | 0.56 | 0.28 | 0.28 / 0.28 | 0.1444 |
| Metal3 | H | 0.56 | 0.28 | 0.28 / 0.28 | 0.1444 |
| Metal4 | V | 0.56 | 0.28 | 0.28 / 0.28 | 0.1444 |
| Metal5 | H | 0.90 | 0.45 | 0.44 / 0.46 | 0.5625 |

- Chip routes **Metal2 … Metal4** (`RT_MIN_LAYER` Metal2 from PDK, `RT_MAX_LAYER` Metal4 from the project). Metal1 is pin
  access plus rails only. Metal5 is unused (PDN_MULTILAYER 0).
- DEF tracks: x = 0.28 + 0.56·k on all four layers, i.e. **every vertical track sits at a site centre** (core origin
  3.36 = 6 sites). Any on-site cell, N or FN, sees the same M2/M4 track set relative to its own origin.
- Row height 3.92 = 7 × 0.56, and row bottoms (3.92 + 3.92r) are multiples of 0.56, so horizontal tracks
  (0.28 + 0.56k) sit at row-relative y = 0.28, 0.84, …, 3.64 in every row. N and FS rows see the same set (symmetric about the row centre). On Metal1 the outer two are under the
  0.6 µm rails, so 5 interior M1 tracks per row; Metal3 has all 7.
- Via1 cut 0.26, enclosure 0.00/0.06 below, 0.01/0.06 above.

## Cells relevant to an adder (LEF width = Liberty area / 3.92 for all)

| Master | Width µm | Sites | Liberty area µm² | Function |
|---|---:|---:|---:|---|
| addf_1 | 18.48 | 33 | 72.4416 | S = A^B^CI, CO = maj |
| addf_2 | 20.16 | 36 | 79.0272 | same |
| addh_1 | 10.08 | 18 | 39.5136 | S = A^B, CO = A&B |
| xor3_1 | 12.88 | 23 | 50.4896 | A1^A2^A3 |
| xnor3_1 | 13.44 | 24 | 52.6848 | |
| xor2_1 | 6.72 | 12 | 26.3424 | |
| xnor2_1 | 7.28 | 13 | 28.5376 | |
| aoi21_1 / oai21_1 / and2_1 / or2_1 | 4.48 | 8 | 17.5616 | |
| nor2_1 | 3.36 | 6 | 13.1712 | |
| nand2_1 | 2.80 | 5 | 10.976 | |
| inv_1 | 2.24 | 4 | 8.7808 | |
| filltie (WELLTAP) / endcap (ENDCAP PRE) | 1.12 | 2 | 4.3904 | physical |
| fill_1 / fill_2 | 0.56 / 1.12 | 1 / 2 | | SPACER |

There is no maj3 cell. **Floor for a full-width ripple chain** with carry-out dropped:
(N−1) addf_1 + 1 xor3_1 → N=22: 21·33 + 23 = **716 sites = 1,571.7 µm²**; N=12: 11·33 + 23 = **386 sites = 847.4 µm²**.
For comparison, the Phase 0 default-ABC mapped area was 2,146.9 / 1,148.1 µm². 716 sites exceed one row (607), so
N=22 needs at least 2 rows.

## Pin geometry (all signal pins Metal1 only; no master has any M2+ pin or OBS)

N orientation, x relative to the cell origin. "Tracks" = M2 track x positions that land inside the pin's x extent.

| Master | Pin | Extent (x; y) | M2 tracks over pin |
|---|---|---|---|
| addf_1 | S (out) | 0.14–0.575; 0.61–3.37 (left edge) | 1 (0.28) |
| addf_1 | A | 1.615–3.47; 1.77–2.15 | 3 |
| addf_1 | CI | 3.89–13.91 strip at y 1.62–1.85, plus a stub | 18 |
| addf_1 | B | 14.64–17.07; 1.795–2.15 | 4 |
| addf_1 | CO (out) | 17.45–17.83; 0.79–3.37 (right edge) | 1 (17.64) |
| addh_1 | CO left edge (1 track), S right edge (1 track), A 8 tracks, B 3 tracks | | |
| xor3_1 | A1 5, A2 8, A3 5, Z 4 tracks | | |
| inv_1, nand2_1 | 1–3 tracks per pin | | |

Implications:
- addf_1 outputs S and CO each offer **one** M2 access column, at opposite cell edges. With every addf_1 in N, CO(i)
  at x0+17.64 and CI(i+1) starting at x0+18.48+3.89 are about 4.7 µm apart in the same row (a short M2/M3 hop). Mirroring (FN)
  puts S on the right and CO on the left.
- The two edge pins (S at 0.14, CO at 17.83) sit within 0.6 µm of the cell boundary. Two N-oriented addf_1 abutting place
  CO(i) (x 17.45–17.83) and S(i+1) (x 18.62–19.055) on adjacent tracks 17.64 and 18.76, one track apart, so a via on each is
  legal. Abutting FN next to N puts two output pins back-to-back; check spacing if that is ever used.
- Pin strips are 0.23–0.38 µm tall on Metal1. A Via1 needs 0.26 + 2×0.06 = 0.38 µm of M1 in one direction, so on the
  thinner strips the router must use the 0.00 enclosure side or a patch. OpenROAD pin access handles this in the baseline chip.
  This is a library-wide property, not a placement-specific risk.
- Wells: VNW is Nwell over y 1.76–4.35 and VPW is Pwell over y −0.43–1.76 (N orientation), each extending 0.43 µm past the cell's
  left and right edges. The cells have **no internal well/substrate tap**, so they need filltie cells nearby.
  DEF power connects `VPWR ← VNW, VDD` and `VGND ← VPW, VSS`.

## Power distribution (from the baseline final DEF and resolved config)

- Metal1 FOLLOWPIN rails 0.6 µm wide on every row boundary, x 3.36–343.28.
- **Metal4 vertical stripes only** (PDN_MULTILAYER 0, so no Metal5 straps): width 1.6, pitch **38.87 µm**, offset 16.32.
  VPWR centres at x = 19.68 + 38.87k, VGND at x = 22.98 + 38.87k (k = 0…8; 9 pairs), y 3.62…157.10.
- Stripe-rail connection: a Via1/Via2/Via3 stack, 3.2 × 1.2 µm (1×3 cuts), at **every** stripe × rail crossing.
  This makes local M2 and M3 obstructions about 3.2 µm wide on every row boundary under each stripe, besides the M4
  stripe itself (about 4 to 5 M4 tracks per stripe).
- 38.87 is not a multiple of the 0.56 site (69.41 sites), so the stripe position relative to the site grid drifts by
  0.23 µm per pitch. A sub-placement that is copied to different x positions will not see identical stripe/via-stack geometry.

## Taps and endcaps (baseline run, step 19 TapEndcapInsertion)

- `WELLTAP_CELL` filltie, `ENDCAP_CELL` endcap, `FP_TAPCELL_DIST` 20 µm. Taps and endcaps are FIXED.
- Endcaps: 2 sites at each row end, x = 3.36 (left) and 342.16 (right).
- Tap pattern found in the DEF (checkerboard, 348 filltie):
  - Odd (FS) rows: x = 42.56 + 39.2k (8 per row).
  - Even (N) rows 2…36: x = 22.96 + 39.2k (9 per row).
  - Rows 0 and 38 (boundary rows): x = 22.4 + 19.04k (17 per row, about double density).
  - In-row tap pitch 39.2 µm = 70 sites, so a row has **68 free sites between consecutive taps**. Exactly two addf_1 (66) fit
    in each tap window, leaving 2 sites. Adjacent rows are staggered by 19.6 µm = 35 sites.
- DRC rule behind this: DF.13_MV / DF.14_MV (KLayout deck, `comp.drc`): max distance from a PCOMP-in-Nwell (NCOMP-in-Pwell)
  device to the well (substrate) tap is **15 µm** for MV (5 V dualgate, which this library uses). In-row tap distance alone can reach
  19.6 µm. The checkerboard works because adjacent rows share wells (N/FS alternation shares Nwell with one neighbour and Pwell
  with the other), so a staggered tap in the neighbouring row is within about 10 µm. Two consequences:
  1. Any custom placement must keep the tool's tap positions, or provide equivalent ones, in **both** rows that share a well.
  2. `RUN_KLAYOUT_DRC` is 0 in the TT config, so the flow never checks DF.13/14. Magic DRC does not cover it.
     Tap compliance of a custom placement must be argued from tap geometry. A clean flow run is not evidence.
- Order of steps in the flow: 17 ManualMacroPlacement → 18 CutRows → 19 TapEndcapInsertion → … → 28 GlobalPlacement → 34 DetailedPlacement.
  Instances fixed at step 17 exist before taps are inserted. CutRows cuts rows only around block (macro) masters, so fixed std
  cells do not cut rows. Unless the fixed cells avoid the tap slots, tapcell could overlap them or skip them. **Check this in the run trees.**

## Flow facts that bear on a fixed std-cell placement

- Synthesis is flat (`synth -flatten`, ABC "AREA 2"). The ripple_add instances are flattened into mac_unit logic. In mac_unit,
  `b = neg ? ~term : term` with `cin = neg` (N=22) and `b = {4'b0, W}`, `a = first ? 0 : L`, `cin = 0` (N=12). Flat synthesis can
  absorb the conditional inversion and the constant bits into the adder. A frozen addf chain cannot: the 22 XORs stay outside,
  and the N=12 adder's top 4 bits (b = 0) and cin = 0 become wasted full adders unless the netlist is specialized (half adders /
  inverters / XOR-with-carry).
- `PL_OPTIMIZE_MIRRORING` true, the resizer runs (repair_design, timing repair post-CTS and post-GRT, buffering and gate cloning on).
  These can resize or replace non-dont-touch cells. A placement claim must show the cells' masters and locations at the final DEF.
- Baseline timing slack: ss setup WNS +41.79 ns on 100 ns. The Phase 2 probe estimated about +20 ns extra SS carry delay
  for an addf_1 chain at N=22. That consumes about half of the slack.
- Baseline std-cell area 46,819.2 µm², 90.09 % utilization, `PL_TARGET_DENSITY_PCT` 92. The die is fixed, so an area saving
  shows up as utilization and routability headroom, not as a smaller die.

## What a reviewer should check (my checklist, fixed before reading the plan)

1. Netlist function at N=22 and N=12 (frozen contract, gate mode), plus my own evaluation of the emitted netlist.
2. Every instance: x on (3.36 + 0.56k), y on (3.92 + 3.92r), orientation ∈ {N, FN} for even r and {FS, S} for odd r, width from the LEF,
   no overlap with each other, with endcaps or with the **tool's tap slots**.
3. Output pins S/CO each have one M2 access column. Verify the placement does not put an M4 stripe or via stack exactly on those
   columns at a row boundary, and that the abutting CO/S tracks are not both blocked.
4. Taps: the placement leaves the checkerboard intact, or the run tree shows taps re-inserted legally.
5. Integration: the cells keep their FIXED location and master through CTS, resizer and detailed placement, at the final DEF, and the
   synthesized netlist really contains the hand cells (not resynthesized, not buffered in between by surprise).
6. Chip-level deltas compared against the noise band of a cosmetic RTL rewrite (n03/n04), not against zero.
