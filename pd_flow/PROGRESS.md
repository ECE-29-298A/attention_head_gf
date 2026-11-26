# Workflow progress (MASTER_WORKFLOW.md)

- Current module: none started (order: ripple_add → max_reg → exp_lut → divider → mac_unit →
  attention_controller → tt_um_attention_head_gf)
- Phase: 0 complete (gate passed 2026-11-26 after user decisions); module 1 ripple_add Phase 1 in progress
- Golden RTL: `pd_flow/baseline/original_rtl` (hashes in `pd_flow/baseline/SHA256SUMS`, HEAD 03de4ac)
- Baseline: `PHASE0_AUDIT.md` (synthesis, harden, regression all recorded)

## Decisions (user, 2026-11-26) on the Phase 0 blockers
- D1: install ngspice: done (`brew install ngspice`, ngspice-47; GF180 inverter smoke test tPHL 90 ps, tPLH 102 ps).
- D2: the baseline slew/cap/fanout violations are an accepted pre-existing waiver. A change must not increase them.
- D3: integrate a custom macro only where it measurably reduces area. Otherwise keep the flat flow and report the macro as evidence.

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
After the decisions: Phase 1 for ripple_add (Agents 1+2), outputs in `pd_flow/modules/ripple_add/`.

## Environment workarounds in place
- sby/eqy: run with `/usr/local/bin/python3 ~/.local/bin/{sby,eqy}`
- Harden: space-free mirror `/Users/samuelzhang/ttharden/attention_head_gf` (rsync, then
  `tt/tt_tool.py --pdk gf180mcuD --harden`); `tt/` copied into the project (untracked)
- Regression: `pd_flow/scripts/regress.sh <logdir>`; area: `pd_flow/scripts/synth_area.py`
