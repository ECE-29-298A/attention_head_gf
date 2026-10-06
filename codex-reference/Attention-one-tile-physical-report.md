# Attention project: measured one-tile physical implementation

Project constraint: **one tile**, including all three attention stages: QK dot products, quantized softmax, and weighted-V accumulation with normalization. This report replaces the earlier 60% synthesis-area screening assumption with a placed, clocked and routed implementation.

## Verdict

The extended `norm_odd` core (NB=7, DB=6, serial multiply) has a concrete layout in **161 × 111.52 µm = 17,954.72 µm²**. Active and support cells occupy **13,865.7984 µm² (77.226% of the tile)** before fillers. This is a measured feasible candidate, not a proof of the absolute largest possible design or the shuttle's final manufacturing approval.

The capacity bound tested for full-range INT8 attention is **128 tokens × 64 dimensions per scheduled head**. Heads and layers are time-multiplexed. The host holds tensors and weights and schedules operations; it does not evaluate attention arithmetic for the hardware path. Capacity here does not mean on-chip tensor storage. The design contains no tensor SRAM.

## Actual layout

![Actual cell placement and metal geometry](Attention-tile-layout.png)

The image is generated from OpenDB cell locations and the transistor/metal GDS. It is not an architectural sketch. `Attention-one-tile.gds` contains the physical geometry, and the archive contains routed DEF, OpenDB, extracted SPEF, per-cell CSV, and all scripts.

## Measured area accounting

| Category | Cells | Area, µm² | Tile fraction |
|---|---:|---:|---:|
| Combinational logic and signal repair | 1,046 | 6,763.9872 | 37.672% |
| Registers | 148 | 3,069.1936 | 17.094% |
| Endcaps | 78 | 292.7808 | 1.631% |
| Well taps | 225 | 281.5200 | 1.568% |
| Clock tree and loads | 32 | 407.8912 | 2.272% |
| Hold repair | 301 | 3,012.8896 | 16.780% |
| Antenna diodes | 15 | 37.5360 | 0.209% |
| Filler cells | 752 | 2,627.5200 | 14.634% |

The core placement rectangle is (2.76, 2.72) to (158.24, 108.80) µm: **16,493.3184 µm²**. This is exactly **13,182 placement sites** (338 columns × 39 rows, each 0.46 × 2.72 µm). Non-filler cells occupy **11,082 sites**. The remainder of the die is margin/pin access. Filler cells occupy the remaining legal row sites and can be replaced during a redesign; their area is not a guarantee that the same area of added logic would route or meet timing.

Power and signal metal lie above the cells. Adding their projected areas to cell area would double count overlapping layers. Their effect was included through actual PDN construction, routing blockages, track capacity, via generation, and detailed routing.

The synthesized, tie-mapped netlist occupied 8,932.3168 µm². Final non-filler overhead relative to that netlist is **4,933.4816 µm²**, including resizing, new signal and hold buffers, clock distribution, antenna protection, well taps and endcaps. Clock tree accounting includes 17 distribution buffers and 15 clock-load cells; this is distinct from the data-path hold-repair cells.

## Verification and timing

- Detailed router: **0 violations** in the final router log.
- Antenna check: **0 net violations and 0 pin violations**, confirmed in the final log.
- Power-grid connectivity was checked for VPWR and VGND.
- KLayout rule reports and LVS results are recorded in `run6/summary.json` and the archived logs. The rule deck enables its implemented FEOL, BEOL and off-grid groups. This is not an assertion that every foundry rule is implemented.
- Final KLayout rule-check totals: **klayout_full_flat.lyrdb: 0 reported items**.
- KLayout layout-versus-schematic: **PASS**, all extracted circuits match.
- No reported maximum transition or capacitance violations at the three tested cell corners.
- RTL functional tests: exhaustive 256-code SiLU, sigmoid, tanh and approximate GELU checks; randomized dot products, normalization and attention; full-range attention boundary cases through 128 × 64; and a captured real SmolLM2 attention-head fixture.
- RTL, the synthesized standard-cell netlist, and the final routed netlist completed a synthetic quantized Transformer block: **16 stages, 2,580 returned bytes, 240,087 cycles**, exactly matching the independent integer reference. This is a small randomly weighted decoder block, not a pretrained language model. At a 10 MHz clock, 240,087 cycles is 24.0087 ms excluding host-side delays.
- The arithmetic tests are bounded functional simulations; no complete formal equivalence proof is claimed.

Post-route extracted timing under a 100 ns clock period (10 MHz):

| Cell-library corner | Worst setup slack | Worst hold slack |
|---|---:|---:|
| Typical, 1.80 V / 25 °C | +85.93 ns | +0.09 ns |
| Slow, 1.60 V / 100 °C | +77.81 ns | +1.06 ns |
| Fast, 1.95 V / −40 °C | +86.71 ns | +0.04 ns |

Interconnect resistance and capacitance were extracted by OpenRCX from routed geometry. The three cell-corner checks use the same nominal interconnect extraction, not separate RC-min/RC-max corners. Constraints include 10 ns maximum and 0 ns minimum I/O delay, 1 ns input transition, 10 fF output load, and 0.5 ns clock uncertainty. The 13 reported unconstrained output endpoints are constant tie outputs. These are explicit design assumptions; a different board/shuttle interface or sign-off corner set requires another timing run.

The first apparently clean routed design had a clock antenna violation and a hold violation after extraction. These were not waived. Diodes and delay cells were added, followed by rerouting and rechecking. Changing a cell or timing constraint can change the result; exact coordinates are exact for the archived implementation.

## What else the same tile does

The original full-attention engine can evaluate nonlinear functions by presenting tiny attention problems. For example, `softmax([0,x]) · [0,x] = x·sigmoid(x)` implements SiLU using existing score, exponential and weighted-sum operations. The integer engine approximates the exponential and quantizes the output; this is not exact real-arithmetic SiLU.

The added linear-output command exposes the existing MAC for projections, residual addition, gating and the multiply-add operations used by RoPE. A compact integer-square-root loop reuses the subtractor and denominator register for quantized RMS normalization. Its denominator is `max(1,floor(sqrt(sum(x_i²))))`; it does not reproduce floating-point epsilon handling exactly. Learned scale uses a subsequent multiply.

The live block test covers RMS normalization, Q/K/V projections, host-supplied RoPE constants, causal full attention, output projection, residuals, and a SiLU-gated feed-forward network. The host supplies data, constants and control sequences.

A separate live RTL demonstration trains a three-parameter logistic classifier and adapts it to changed labels. Arithmetic updates happen in the tile model; weight storage and scheduling are external. Held-out accuracy on 16 fixed toy examples moved from 50% to 100% after one epoch for the first rule, then from 31.25% to 100% after one epoch after the rule changed. This demonstrates reuse for simple learning, not LLM training or a meaningful generalization benchmark.

The nonlinear attention identity has prior art; no new mathematical breakthrough is claimed. The engineering result is a tested shared datapath and a physically implemented one-tile candidate.

## Why the earlier 60% statement was inadequate

Tiny Tapeout's template uses a **placement-density setting** of 60 and explicitly discusses higher values. It is not a physical law that clocks consume the remaining 40%. Synthesis cell area, placement density, core occupancy, wiring congestion and final filler occupancy are different measurements. The earlier exclusion list also disallowed many small ordinary gates while permitting special low-power cells; the physical run uses a corrected cell selection and matching physical libraries. Earlier area numbers therefore must not be compared directly as an isolated architectural improvement.

This flow explicitly constructs the clock network, PDN, taps, endcaps, timing repairs, antenna repairs and fillers, then routes their connections. It answers whether **this implementation** fits. Finding a global maximum over architectures, precisions, serial schedules and host-storage arrangements is a separate optimization problem; no single percentage can establish that maximum.

## Remaining sign-off scope

This custom OpenROAD feasibility run does not replace the actual shuttle's approved LibreLane/PDK setup, precheck, complete sign-off rule deck, power-integrity analysis, extraction corners or final integration checks. It does not measure fabricated silicon or prove a power limit. The target shuttle/process has not been finalized; a different process changes the result.

## Reproduction and sources

The archive includes source RTL, integer oracles, simulation harnesses, synthesis and physical scripts, physical libraries and their SHA-256 manifest, gate netlists, final layout, reports and intermediate checkpoints. Large tool binaries are excluded. See `physical/README.md` and `physical/reproduce.sh`.

- Tiny Tapeout template and settings: https://github.com/TinyTapeout/ttsky-verilog-template/blob/main/src/config.json
- One-tile pin template: https://github.com/TinyTapeout/tt-support-tools/blob/main/tech/sky130A/def/tt_block_1x1_pg.def
- SKY130 physical platform: https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/tree/master/flow/platforms/sky130hd
- SS/FF Liberty libraries: https://github.com/efabless/skywater-pdk-libs-sky130_fd_sc_hd/tree/master/timing
- OpenROAD binary used: https://github.com/Precision-Innovations/OpenROAD/releases/download/2024-12-14/openroad_2.0-17598-ga008522d8_amd64-ubuntu-22.04.deb
- OpenRCX extraction documentation: https://openroad.readthedocs.io/en/latest/main/src/rcx/README.html
- Huben and Morris (2023), attention-only transformations: https://arxiv.org/abs/2309.08593

The GDS export includes a top-level non-mask substrate marker (236/0), required by the ORFS LVS deck to represent continuous substrate across tap cells. This fixes an extraction annotation omission; it does not alter conductive masks or waive a mismatch.
