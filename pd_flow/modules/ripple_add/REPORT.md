# Module 1: `ripple_add`, report

Workflow: `MASTER_WORKFLOW.md` (user decisions D1 to D5 in `pd_flow/PROGRESS.md`). Date: 2026-11-26.
**Outcome:** verified, optimization explored, custom placement implemented and signed off as a
standalone block. **The shipped chip keeps the golden RTL (D3):** the custom block does not
reduce chip area and costs setup slack and power.

## 1. Specification and invariants
`ripple_add #(N)`: combinational, `s = (a + b + cin) mod 2^N`, carry out dropped. It is used in
`mac_unit` as N=22 (shared score/V adder; `b = ~x, cin = 1` gives `a − x`) and N=12 (weight sum,
cin = 0). There is no state and no clock. The requirements R1–R8 are in `verif/SPEC.md`, with
traceability in `verif/RTM.md`.

## 2. Verification (Phase 1, gate `PHASE1_GATE.md`)
| Evidence | Result |
|---|---|
| Formal (SBY smtbmc/Z3, depth 1, stateless model, so complete) | **proven** for N = 1,2,3,4,5,7,8,12,16,22,32,64; abc pdr also proves N = 12, 22. Each run takes 0.3–0.6 s |
| Covers | 16/16 reached (5 on the output); the negative control fails as expected |
| Simulation | exhaustive N ≤ 12 (N=12: 2^25 inputs, checksum); N=22: 216,556 golden vectors on Verilator and Icarus, plus 50 M random |
| Gate level (GF180 netlists) | N=22 10/10, N=12 11/11 |
| Mutation (Agent 2) | 22/22 non-equivalent mutants killed. 3 equivalent survivors are proven equivalent (SBY miter, EQY). A 1-in-2^45 input mutant is killed only by formal |
| Assumptions | none |
| Contract hash | `b879560878477abf` (17 files, `CONTRACT.sha256`) |

Limitations: only Icarus is 4-state (Verilator is 2-state); the checks cover N ≤ 64.

## 3. Optimization (Phase 2, gate `PHASE2_GATE.md`)
There were 17 candidates and 240 operand-order variants, all EQY-proven equivalent to the golden.
Anything smaller is slower. The original is on the area/delay front and is **retained**.

| | Area (synth_area, N=22) | Shipped-flow chip synthesis |
|---|---:|---:|
| golden | 2,146.9 µm² | 41,116.1 µm² |
| best candidate c01 (behavioural) | 2,107.4 µm² (+12% delay) | 42,308.1 µm² (**+1,192**) |

Method finding: default-ABC area does not predict the shipped area at chip level.
Acceptance now uses `scripts/ll_synth.sh`.

## 4. Placement planning (Phase 3, gate `PHASE3_GATE.md`)
- Cell implementation: hybrid `addf_1` × (N−1) plus an `xor3_1` MSB with the carry on A3 (fast pin).
- Tetris placement: one bit per row, a 33-site (18.48 µm) column at the area bound.
- Integration via `MACRO_PLACEMENT_CFG`. `MANUAL_GLOBAL_PLACEMENTS` was rejected because it is a hint that drifts.
- Independent review: approved in round 2. The round-1 blocking finding was the MSB carry on the
  slow pin, costing 1.95 ns, which had been misattributed to noise.

## 5. Implementation and signoff (Phase 4, gate `PHASE4_GATE.md`, details `impl/IMPLEMENTATION.md`)
Standalone blocks: LibreLane 3.0.14, placement FIXED, automatic routing on Metal2–Metal4.

| | N=22 | N=12 |
|---|---|---|
| Die / core | 27.44 × 94.08 µm (2,581.56 µm²) / 1,786.89 µm² | 27.44 × 54.88 µm (1,505.91 µm²) / 974.67 µm² |
| Custom bounding box | 18.48 × 86.24 = 1,593.72 µm² (98.6% utilization) | 18.48 × 47.04 = 869.30 µm² (97.5%) |
| Devices (Magic extraction) | 612 | 332 |
| Magic DRC / route DRC | 0 / 0 | 0 / 0 |
| KLayout full deck (651 rules, feol/beol/offgrid), DF.13/14 | 0, 0/0 | 0, 0/0 |
| KLayout antenna | 0 | 0 |
| KLayout density | **7 (whole-die fill rules; project-level, see gaps)** | 7 |
| LVS: Netgen / KLayout transistor-level | match uniquely / match | match uniquely / match |
| LVS negative controls | pin swap fails (Netgen); topology change fails (KLayout) | — |
| Post-layout SPICE function (ngspice-47, PEX) | 19/19 at tt, ss, ff | tt only |
| Frozen contract on the extracted netlist | proven + sampled | proven + exhaustive |

### Characterization, N=22 (input slew 0.30 ns, 20 fF per output)
| | tt 25 °C 3.3 V | ss 125 °C 3.0 V | ff −40 °C 3.6 V | Source |
|---|---:|---:|---:|---|
| Worst delay b[0]↓ → s[21] | 22.11 ns | 44.04 ns | 12.66 ns | SPICE (Magic PEX, C only) |
| Worst delay | 19.97 ns | 41.51 ns | 11.04 ns | block Liberty (OpenSTA + SPEF) |
| Energy per operation (each input bit toggles with p = 0.5) | 6.42 pJ | 5.17 pJ | 8.07 pJ | SPICE |
| Leakage | 0.07 nW | 0.93 nW | 0.06 nW | SPICE, gmin 1e-15 |
| Input capacitance a / b / cin | 11.5 / 10.5 / ≈10.5 fF | | | SPICE, within 10% of Liberty |

N=12, tt: SPICE worst delay 11.95 ns, Liberty 11.10 ns.

Views (sha256 in `impl/views/views_n{22,12}.json`, structural cross-check PASS across 22 views):
GDS, LEF, DEF, nl/pnl Verilog, behavioural Verilog, CDL, SPICE/PEX, SPEF (min/nom/max),
Liberty (tt/ss/ff).

## 6. Area summary (reported separately, as the workflow requires)
| Measure | Golden RTL | Custom hybrid |
|---|---:|---:|
| Mapped cell area, module (synth_area, N=22 / N=12) | 2,146.9 / 1,148.1 µm² | 1,571.7 / 847.4 µm² |
| Custom bounding box (N=22 / N=12) | — | 1,593.72 / 869.30 µm² |
| Standalone block die (N=22 / N=12) | — | 2,581.56 / 1,505.91 µm² |
| Chip, automated implementation, std-cell area | 46,819.2 µm² (baseline) | 47,040.9 µm² (`fixed_a3`) |
| Chip, allocated die | 55,712 µm² (1×1 tile) | 55,712 µm² |

## 7. Integration
The integration path is demonstrated in the chip run `layout_plan/chip_runs/fixed_a3`:
- Integration check: `impl/integration/chip_netlist_check.json` ALL_PASS. The final netlist has exactly the 22 + 12 frozen cells FIXED at the configured coordinates, a buffer-free carry chain, and no resynthesis.
- Physical: chip DRC (KLayout main) 0, antenna 0, LVS 0.
- Chip timing and power: ss setup WNS 25.26 ns, against 41.79 ns for the baseline; slew/cap/fanout 399/0/11; vectorless power 3.60 mW, against 3.05 mW.
- The gate-level top test passes (3 pass, 1 skip for missing SmolLM data) only with flop models initialized at t = 0. With the stock PDK models, every netlist, including the baseline, fails at 31 ns. The unreset datapath flops start at X, and cocotb's clock starting high at t = 0 is treated as a rising edge. This is a simulation-model artifact, not a design defect, and later modules will prove independence from initial values formally.
- Not adopted in the shipped chip (D3): no chip-level area gain, −16.5 ns ss slack, +0.55 mW.

## 8. Open gaps
1. Density (fill) rules: 7 at block level and 5 on the unmodified baseline chip. The TT flow runs no fill and keeps `RUN_KLAYOUT_DRC` off. This is a project-level item, not suppressed.
2. SPICE is 6–15% slower than Liberty. The gap reproduces inside a single PDK `addf_1`
   (Magic extraction of the cell, 0.81 ns, against PDK Liberty 0.70 ns), so it is not caused by
   routing. Which value is right is unresolved. The chip slack margin covers it.
3. The PEX has capacitance only. Wire R is in the SPEF/STA path, not in SPICE.
4. Block PDN offset 7.91 µm instead of the planned 16.32 µm (PDN-0185 in a 20.72 µm core).
5. N=12 SPICE ran at tt only.
6. The gate-level top test needs initialized flop models (`impl/scripts/make_gl_models.py`).

## 9. Reproduction
- Contract: `verif/run_all.sh [--rtl F --out D] [--gate N]`
- Mutation: `review/run_mutation.sh`
- Optimization: `opt/eval_full.sh <cand>`
- Shipped-flow area: `../../scripts/ll_synth.sh <rtl_dir> <tag>`
- Placement: `layout_plan/gen_placement.py`, `validate_placement.py`
- Implementation, all steps: `impl/scripts/reproduce_all.sh` (commands in IMPLEMENTATION.md §10)
- Full harden trees: `/Users/samuelzhang/ttharden/ra_*` (on disk, not in git)

7. Latent bug, no effect here: `verif/gate/extract_cells.py` misses unnamed UDP instances written as `udp(`. ripple_add has no flops, so it is unaffected; later modules use the fixed copy in `modules/max_reg/verif/gate/`.
