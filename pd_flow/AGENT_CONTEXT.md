# Shared context for workflow agents

Project root: `/Users/samuelzhang/Desktop/2B ECE/attention_head_gf` (**the path contains a space:
quote every path** in shell, Yosys, SBY and EQY scripts; in `.sby`/`.eqy` `[files]` sections,
copy files in or use relative paths rather than absolute ones).
Read `pd_flow/PHASE0_AUDIT.md` first: the hierarchy, invariants, CDC/reset rules, baseline
metrics and tool notes are there.

## Rules
- Golden (original) RTL: `pd_flow/baseline/original_rtl/`. Never edit it.
- Work only inside your module directory `pd_flow/modules/<module>/<phase>/`, unless your brief
  says otherwise. Do not edit `src/`, `test/`, `info.yaml`, the reference project, the PDK or
  installed tools. Do not commit or push. The orchestrator commits.
- Never weaken a check to make it pass. Report failures, counterexamples and timeouts as they are.
- Label every result as one of: proven (unbounded), bounded-pass (depth k), failed,
  timed-out, unsupported, inconclusive. A cover witness or bounded pass is not a proof.
- Keep logs, counterexamples/witnesses and machine-readable results (JSON) in your directory.
- CPU budget: at most 8 concurrent jobs in total. Do not nest parallelism.

## Tools (native macOS)
```bash
export PATH="/Library/Frameworks/Python.framework/Versions/3.12/bin:$HOME/.local/bin:/opt/homebrew/bin:$PATH"
PY=/usr/local/bin/python3                 # has cocotb 2.0, pytest, click, numpy
$PY ~/.local/bin/sby -f x.sby             # SymbiYosys: MUST be run with this python
$PY ~/.local/bin/eqy -f x.eqy             # EQY: same
yosys (0.71), yosys-smtbmc, z3, yosys-abc, verilator 5.046, iverilog/vvp, ngspice-47
```
Working smoke references: `/Users/samuelzhang/formal_tools/smoke_test/counter.sby`
(k-induction) and `example.eqy` (SAT equivalence).

Existing regression: `pd_flow/scripts/regress.sh <logdir>` (all suites, about 30 s).
Mapped area: `pd_flow/scripts/synth_area.py [--rtl DIR] [--out JSON] [module ...]`, with module
names as in its TARGETS table.

## Physical (Docker, LibreLane 3.0.14)
```bash
source /Users/samuelzhang/ttsetup/env.sh   # PDK_ROOT, PDK=gf180mcuD, docker on PATH
IMG=ghcr.io/librelane/librelane:3.0.14
PDKV=/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee
docker run --rm -v "$PDKV:$PDKV" -v "<work>:<work>" -w "<work>" $IMG bash -lc '...'
```
The container has openroad, opensta, magic, netgen, klayout 0.30.7, yosys 0.62. Docker memory
is 7.65 GiB. Mount space-free host paths only, such as `/Users/samuelzhang/ttharden/...`, and
copy results back into `pd_flow/`. GF180 PDK (gf180mcuD): `$PDKV/gf180mcuD/libs.tech/{klayout,magic,netgen,ngspice}`,
`libs.ref/gf180mcu_fd_sc_mcu7t5v0` (7-track cells used by the chip). Hardware tetrising
method: `/Users/samuelzhang/Desktop/HW_tetrising_ai/*.md`.

## Host KLayout (works natively, preferred for layout scripting and DRC)
```bash
K=/Applications/klayout.app/Contents/MacOS/klayout    # KLayout 0.30.14; batch: $K -b -r script.py|.drc -rd var=value
DRC=$PDKV/gf180mcuD/libs.tech/klayout/tech/drc/gf180mcu.drc
$K -b -r $DRC -rd input=x.gds -rd topcell=X -rd report=x.lyrdb -rd feol=true -rd beol=true -rd offgrid=true -rd run_mode=deep
```
LVS deck: `$PDKV/gf180mcuD/libs.tech/klayout/tech/lvs/`. Reference point: the PDK's own
`gf180mcu_fd_sc_mcu7t5v0__addf_1`, checked standalone, reports 4 items (DF.13_MV, DF.14_MV).
These are probably well/tap context rules that clear once the cell sits in a placed row
(unconfirmed). Compare a custom cell standalone against this and in-row context separately.
`python3 -c 'import klayout.db'` is not installed on the host. Use `$K -b -r` for Python
scripts (the `klayout.db`/`pya` API is available inside).

## Layout scope (user decision D4, overrides the workflow's transistor-level wording)
Custom layout means **custom placement of existing GF180 7-track standard cells only**
(tetrising). Do not design transistor-level cells. Do not hand-draw routing.
Connections between cell ports are made by automatic routing (OpenROAD global and detailed
routing) with the placement fixed. Use as little manual routing guidance as possible. Routing
relief that changes placement, such as spacing or filler, is allowed. The Phase 3 deliverable
is a scripted, coordinate-level cell placement (row, site, orientation per instance) plus the
gate-level netlist it places. Phase 4 generates the placement, fixes it, routes it
automatically, then runs DRC, LVS, extraction and characterization.

## End goal (user decision D5)
Tetris module by module, then tetris the **whole chip together as one standard-cell placement**.
Design each module's placement as a reusable sub-placement (relative coordinates, a
row-aligned footprint, port side and pin order) that composes into the full 1×1 tile
(die 346.64 × 160.72 µm, core 51,967 µm²), rather than as a hard macro with halos. Benchmark
from the user's earlier work: about 80% power, 20 to 50% area, about 20% timing improvement.
Baseline: 3.05 mW tt, 46,819.2 µm² std-cell area, 90.09% utilization, ss setup WNS +41.79 ns
on 100 ns. Power is dominated by switched capacitance (wires and clock). Report it per
module with stated activity.

## Result labels (orchestrator ruling)
`pass-static` is accepted for static checks: lint, structure, interface, build, cell extraction.
It is evidence, not a proof. Simulation uses `pass-exhaustive` / `pass-sampled`.

## Area measurement (orchestrator ruling after ripple_add Phase 2)
`synth_area.py` (default ABC) does not predict the shipped area at top level. For one
candidate it reported −1,008 µm² where the shipped flow gave +1,192 µm². Top-level
acceptance uses the **shipped flow**: `pd_flow/scripts/ll_synth.sh <rtl_dir> <tag>`
(LibreLane 3.0.14 in Docker, project config, stops after Yosys.Synthesis, about 30 s; prints
`tag area cells`; baseline 41,116.096 µm², 1,434 cells). `<rtl_dir>` must hold all 7 shipped
files. Run at most 2 at once (Docker memory). Use `synth_area.py` for module-level exploration only.

## Rulings after ripple_add Phase 3 (orchestrator)
- **Violation-count noise (D2 applied):** cosmetic rewrites of the unchanged RTL move the harden
  slew/cap/fanout counts to 260–381 / 1–2 / 11–13 (two samples; widen the band as more noise
  runs come in). "No increase" means staying inside that band. Report exact counts every time.
- **Harden noise:** near-identical netlists vary by about 75 µm² std-cell area and a few ns of
  setup slack. The flow itself is deterministic (identical inputs give bit-identical runs).
  Before calling a difference "noise", diff the netlists. A pin swap is not noise.
- **Integration mechanism for fixed std-cell placement:** `MACRO_PLACEMENT_CFG`, which keeps the
  cells FIXED at exact coordinates through the flow. `MANUAL_GLOBAL_PLACEMENTS` is only a hint
  (the detailed placer moves and mirrors cells). `RSZ_DONT_TOUCH_RX` breaks the resizer
  (RSZ-3006). The chip's fixed tap cells leave windows exactly 33 sites wide.
- **Unit of tetrising:** a frozen leaf block cannot absorb the surrounding logic that ABC folds
  into it (operand inversion, muxes, constants). Evaluate tetris gains at mac_unit bit-slice
  level, and compare a placement-only approach that keeps ABC's in-context mapping.

## Notes from max_reg Phase 1
- For gate-level contracts with flops, use `modules/max_reg/verif/gate/extract_cells.py`, not the
  ripple_add copy. The ripple_add copy misses unnamed UDP instances written without a space before
  `(`, which is harmless there (no flops), and that contract stays frozen as is.
- The sequential contracts accept only positive-edge flops clocked directly by `clk`. **Clock
  gating**, a key power lever (the mac ring shifts every clock), needs a reviewed contract
  extension: a gated-clock formal model plus equivalence to the ungated golden under the enable.
