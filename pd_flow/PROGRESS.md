# Workflow progress (MASTER_WORKFLOW.md)

- Current module: 2 max_reg (module 1 ripple_add COMPLETE, `modules/ripple_add/REPORT.md`)
- Phase: re-plan under D7. max_reg Phases 1-2 done; its standalone Phase 3 was stopped (plan rev 2 kept as a building block). Chip partition and floorplan (architect agent) in progress; chip-flow area experiment running.
- Golden RTL: `pd_flow/baseline/original_rtl` (hashes in `pd_flow/baseline/SHA256SUMS`, HEAD 03de4ac)
- Baseline: `PHASE0_AUDIT.md` (synthesis, harden, regression all recorded)

## Decisions (user, 2026-11-26) on the Phase 0 blockers
- D1: install ngspice: done (`brew install ngspice`, ngspice-47; GF180 inverter smoke test tPHL 90 ps, tPLH 102 ps).
- D2: the baseline slew/cap/fanout violations are an accepted pre-existing waiver. A change must not increase them.
- D3: integrate a custom macro only where it measurably reduces area. Otherwise keep the flat flow and report the macro as evidence.

- D4 (user, 2026-11-26): tetrising custom-places standard cells only. Connections between cell ports
  are routed automatically by the tool (OpenROAD global and detailed routing, placement fixed)
  as far as possible. No transistor-level custom cells and no hand-drawn routing. Phase 3 plans a
  coordinate-level cell placement. Phase 4 generates it from a script, fixes it, and routes it automatically.

- D5 (user, 2026-11-26): stick with standard cells as far as possible. Tetris module by module,
  then tetris the entire chip together as one placement (the final integration step). Each
  module's placement is a reusable placement recipe or sub-placement that composes into the
  whole-chip placement, not necessarily a hard macro. Benchmark from the user's earlier work:
  about 80% power, 20 to 50% area, about 20% timing-closure improvement. Measure against the
  Phase 0 baseline: 3.05 mW (tt), 46,819.2 µm² std-cell area at 90.09% utilization, setup WNS
  +41.79 ns at ss_125C_3v00 on 100 ns (critical path about 58.2 ns). Report the measured
  improvement per metric honestly, whether or not the targets are met.

- D6 (user, 2026-11-26): "dont worry too much about timing, focus on MINIMIZING AREA with physical
  design". Area is now the primary objective. Timing only has to stay legal: setup and hold WNS
  >= 0 at every corner on the 100 ns clock, so the chip still works. Lost slack is no longer a
  reason to reject an option. Still required: signoff (DRC, LVS, antenna), hold, the verification
  contracts, no new slew/cap/fanout beyond the D2 noise band, and the TT tile and pins.

- D7 (user, 2026-11-26): "Placement always should generate area savings, since automatic place and
  route sucks. The physical design of a module should account for the physical design of its
  dependencies. Without shared stuff, things like the SPI modules should be their own fully custom
  designed layouts in their own isolated blocks, but shared items like max-reg should be physically
  designed in mind with other modules. ... Physical design will work BEST when all modules have
  physical design and then can be grouped/placed as one."

  Consequences:
  - Do not run a per-module chip harden as an accept/reject gate.
  - Partition the chip into **isolated blocks** (no shared logic, e.g. the SPI/config interface)
    and **coupled clusters** (e.g. mac_unit + max_reg + ripple_add). Each cluster is synthesized
    and placed together, with its neighbours' port locations as constraints.
  - Assemble the whole chip with every cell custom placed (routing stays automatic, D4), and
    evaluate it at chip level.
  - Per-module Phase 1 (verification contract) and Phase 2 (RTL optimization) continue, because
    every netlist still needs a verified contract.
  - Per-module Phase 3/4 are replaced by cluster- and chip-level physical design.
  - ripple_add's and max_reg's standalone blocks are kept as building blocks and references only.

## Blockers as raised at Phase 0 (resolved by D1 to D3)
1. No SPICE simulator (ngspice/Xyce) on host or in the LibreLane container. Phase 4 requires
   post-layout SPICE verification and characterization. Proposed fix: `brew install ngspice`.
2. Baseline harden has 381 max-slew, 1 max-cap and 11 max-fanout violations, caused by the
   preserved `src/config.json` repair settings. The final physical gate cannot be "clean"
   unless those settings change or the violations are accepted as a pre-existing waiver.
3. Per-module hard-macro integration into a 90%-full 1×1 tile, with nested macros
   (ripple_add in mac_unit in controller), is likely to raise area or fail placement. That
   conflicts with the area objective. Proposed: integrate a macro only where it measurably
   reduces area, and otherwise keep the flat flow and report the macro as evidence.

## Exact next action
Wait for the chip partition report (`pd_flow/chip_partition/`) and the chip-flow area experiment (`pd_flow/chip_flow_area/`). Then run Phase 1+2 for the remaining modules (exp_lut, divider, mac_unit, attention_controller, top), and do physical design per cluster in the partition order.

## Completed modules
- ripple_add: golden retained; standalone tetris block signed off (DRC/LVS clean, SPICE characterized); not integrated (D3).

## Environment workarounds in place
- sby/eqy: run with `/usr/local/bin/python3 ~/.local/bin/{sby,eqy}`
- Harden: space-free mirror `/Users/samuelzhang/ttharden/attention_head_gf` (rsync, then
  `tt/tt_tool.py --pdk gf180mcuD --harden`); `tt/` copied into the project (untracked)
- Regression: `pd_flow/scripts/regress.sh <logdir>`; area: `pd_flow/scripts/synth_area.py`
