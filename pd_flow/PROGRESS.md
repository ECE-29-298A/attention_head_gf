# Workflow progress (MASTER_WORKFLOW.md)

- Current module: 2 max_reg (module 1 ripple_add COMPLETE, `modules/ripple_add/REPORT.md`)
- Phase: divider Phases 1-2 PASSED (contract 549f089fd92465c1; c06 ACCEPTED, chip -367 um2, cone -676). Next: mac_unit Phases 1+2. Datapath tetris done (xpk20_s1, -4.4, hold +0.034); needs re-map after c06.
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

- S1 (user, 2026-11-26): parallel-execution supplement. Agents 1, 2 and 3 run concurrently per module,
  each in an isolated workspace with an immutable snapshot; the acceptance gates are unchanged. Still one
  module at a time. See AGENT_CONTEXT "Parallel execution".

- F1 (orchestrator, 2026-11-26): accepted chip flow-config delta `pd_flow/chip_flow_area/recommended_config.patch`
  (h2). Verified against the raw metrics.json:
  - std-cell 46,819.2 -> 45,475.8 µm² (-1,343.4, -2.87%); the synthesized netlist is bit-identical;
  - setup WNS >= 41.79 ns and hold WNS >= +0.058 ns (ff) at all corners;
  - slew/cap/fanout 281/2/6; DRC/LVS/antenna 0; power 2.934 mW.

  **Not yet applied to src/**, because applying it mid-module would shift the ll_synth noise band of
  running comparisons (EXTRA_EXCLUDED_CELLS also restricts ABC). It is applied at chip assembly,
  and h2 (`/Users/samuelzhang/ttharden/fx_h2_k6`) is the reference for cluster and chip
  evaluation. Risk: the ff hold margin falls to +0.058 ns; the fallback is `alt_holdsafe_config.patch`
  (h3, +0.076 ns, -1,185.4 µm²).

- D8 (user, 2026-11-26): "make sure tetrising agents work at MAX effort. i expect up to 90% packing density on
  physically designed modules". Every tetrising, placement or floorplan agent is spawned with effort=max.
  Each custom-placed block or cluster targets about 90% packing: cell area over placement-region area,
  taps included, with the region a rectangle or a union of row segments. A block below 85% needs a measured
  reason (pin access, routability, a DRC hazard).

- D9 (user, 2026-11-26): "do NOT do exhaustive testing. you MUST use formal verification techniques."
  - Acceptance evidence is formal: equivalence or property proofs (SBY k-induction/pdr, EQY), covers and
    negative controls.
  - Exhaustive simulation is not run.
  - X-propagation is checked formally, not with 4-state exhaustive simulation.
  - Mutants must be killed by a formal item.
  - Cheap sampled simulation may stay as non-gating smoke only.
  - Frozen contracts (ripple_add, max_reg) already rest on unbounded proofs. Their exhaustive items are
    dropped from reruns through a reviewed amendment the next time those contracts are touched.

- D9b (user, 2026-11-26): "you also dont need to do full formal for everything. Combination circuits only need
  edge cases and spot checks."
  - **Combinational logic:** directed edge cases plus random spot checks (seconds, not exhaustive), with
    no full formal proof required.
  - **Sequential behaviour** (state, reset, latency, power-up): formal (SBY k-induction or pdr), with
    covers and negative controls.
  - **Optimized candidate vs golden:** EQY equivalence stays mandatory, as the workflow's equivalence
    gate (it costs about 1 s).
  - Exhaustive simulation stays banned (D9).

- F2 (orchestrator, 2026-11-26): accepted `pd_flow/chip_flow_area/min_drive/recommended_config.patch` (x0) on top of F1:
  a project-level `PNR_EXCLUDED_CELL_FILE` that allows `mux2_1`. The PDK has excluded it since 2022 because of a Magic
  CO.6 false positive (gf180mcu std-cell issue #23; Magic tech fixed 2022-11-30). It is DRC-clean on Magic, the PDK
  KLayout deck and the TT precheck KLayout and antenna decks, alone, abutted in every orientation, in a routed
  block and in the chip.
  - Result (orchestrator-checked metrics): 45,475.8 -> 44,911.6 µm² (-564.2); slew/cap/fanout 242/1/0; setup >= +43.16 ns.
  - **Hold margin is only +0.007 ns at ff, -40 °C.** The final choice between x0 and the hold-safer x3 (clkbuf_16 root,
    -406.1 µm², +0.036 ns, screened only to step 55) is made at chip assembly with a signoff harden.
  - Forcing minimum drive on logic does not save area: banning upsizes adds buffers (+17 to +1,809 µm²).
  - Cumulative against the original baseline: 46,819.2 -> 44,911.6 µm² (-1,907.6, -4.07%).

- D10 (user, 2026-11-26): the Tetris method's objective is swapped from energy to **area**. The project override is
  `pd_flow/TETRIS_AREA_OBJECTIVE.md`; it wins over the reference where the two conflict. Every placement agent must
  read the reference files by their real names (`tetris_layout_*.md`) and document each method step and gate in
  its PLAN.md. Audit of earlier work: only the ripple_add plan cited the method explicitly. The max_reg and
  architect plans used parts of it (generator plus validator, bounds, fixed-placement routing) without following
  its 12 steps. The orchestrator's briefs had also given the wrong file names (`SKILL.md`/`method.md`).

- D8b (user, 2026-11-26): "when you restart, please reduce the agents effort from max to high". Tetrising, placement
  and floorplan agents now run at effort=high, not max. The ~90% packing target is unchanged.

- D8c (user, 2026-11-26): "the 90% packing target, dont start as a target, just note as a potentially achievavle bound.
  stop when packing density seems to converge." ~90% is an upper bound to note, not a goal. Agents pack only while
  dry-run area keeps improving, and stop once packing density converges (successive tighter trials give no
  further area gain, or stop compacting). The earlier "below 85% needs a measured reason" rule is withdrawn.

- D11 (user, 2026-11-26): "lets try to place the whole chip at once since individual module optimizaiton doesnt seem
  to be buying much in area, given our chip already has very high density as is". Per-region placement (divider,
  ctrl, SPI) is dropped. One whole-chip tetris runs on the netlist with c06 (`pd_flow/chip_tetris/`, reference
  `~/ttharden/wc_ref`). mac_unit Phase 1+2 keeps running, because its result changes the netlist the placement
  must be redone on.

- Signoff with divider c06 (wc_ref, 2026-11-26, orchestrator-checked): 44,777.7 um2 (-133.9 vs x0 44,911.6; the
  synthesis estimate was -367). Slew/cap/fanout 195/1/7 (fanout 0 -> 7, inside the D2 band of 13). Setup +45.2,
  hold +0.105 ns (x0 +0.007). DRC/LVS 0. Power 2.939 mW (+5.6%, diagnostic).
- mac_unit c09 (provisional; contract 037dffd RTL 24/24, gate 13/13, EQY by name): synthesis -727 um2 with c06.
  The whole-chip tetris reference moves to wc_ref2 = c06 + c09.

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
