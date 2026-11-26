# Tetris method: area-first override for this project (user decision D10, 2026-11-26)

The reference method is `/Users/samuelzhang/Desktop/HW_tetrising_ai/`:
- `tetris_layout_SKILL.md`
- `tetris_layout_method.md`
- `tetris_layout_routing-closure.md`
- `tetris_layout_experiments.md`
- `tetris_layout_energy-measurement.md`

Its objective is **energy per operation**. On this project the user replaced that with **area**:
"I saw the minimize energy condition. this should be swapped for area." Everything else in the
method still applies: the physical contract, the 12-step workflow, generator plus validator,
fixed-placement routing, failure classification, one relaxation at a time, and the gates. Where
this file and the reference conflict, this file wins.

## 1. Objective (replaces method.md §1)
Minimize the **total std-cell area the chip needs**, which is the shipped flow's
`design__instance__area__stdcell` after signoff, and the **placed footprint** of each block or
cluster.
- **What placement can move:** it never changes a cell's own area. It changes the area the flow
  adds afterwards, through timing-repair buffers, resizer upsizing and the clock tree, plus the
  whitespace inside a region. Reference h2/x0 shows that this overhead is about 2,500 µm² (`AGENT_CONTEXT.md`).
- **Proxies before signoff:** use B's dry run (`chip_partition_b/scripts/pilot_dryrun.py`), which
  reproduces the harden's area. Under that, use HPWL and the count of driver pins needing repair;
  long or overloaded nets are what create repair buffers and upsizes.
- **Constraints, not objectives:** energy, delay and wire length.
  - Timing: WNS >= 0 at every corner on the 100 ns clock (D6).
  - Violations: slew/cap/fanout inside the D2 band.
  - Packing: ~90% is a possible bound only (D8c). Tighten while area improves; stop when density converges.
- **When a denser outline counts:** only if the dry run or signoff confirms that the flow's added
  area did not grow by more than the whitespace saved.

## 2. Cost function (replaces method.md §4 "Cost function"; checked in this order)
1. Arithmetic, phase and placement legality.
2. **Std-cell area after repair and CTS** (dry-run measured): fewer repair buffers, fewer upsizes,
   a smaller clock tree.
3. **Region footprint and packing:** smallest footprint that still improves area; stop when density converges (D8c). ~90%, taps included, is a bound, not a goal.
4. Nets most likely to need repair kept short: high-fanout broadcast and control nets, the clock
   spine, and long datapath nets. Weight a net by how close its driver is to its slew/cap limit,
   not by its activity.
5. Pin access and clean region boundaries.

"Every added site needs a named reason" still holds. Do not accept tool-inserted buffers or
upsizing without accounting for their area.

## 3. Gates (replaces method.md §8 G3; G0–G2.5 and G4 unchanged)

| Gate | Evidence | Pass | Stop if |
|---|---|---|---|
| G3 (area) | Dry run, then signoff harden; std-cell area by class and census per master; footprint per region | Area below the reference (h2 or x0), attributable by class, with timing legal and D2 met | No area win, or timing/D2 illegal |

Energy, power and switched capacitance are reported as diagnostics only (vectorless power from
the harden). `energy-measurement.md` is read only when a power number is quoted.

## 4. How the method is applied here (orchestrator rules)
- Every placement agent reads all of the reference files above, by their real names, plus this file.
- Its PLAN.md has a section per method step (1–12) and per gate (G0–G4). Each section says what
  was done, the evidence path, or why the step does not apply.
- Synthesis stays flat (`chip_partition_DECISION.md`). The "grammar" (step 4) is applied by
  placing the flat netlist's cells, attributed to their modules, so cross-module optimization is
  not lost.
- "Two placements, both worth keeping" (method §4) maps onto this project as follows:
  - the pure-Tetris packing bound;
  - a wire-aware seed built from the tool's placement.

  Keep both, and compare them by dry-run area.
