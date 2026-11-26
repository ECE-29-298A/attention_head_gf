# exp_lut: Phase 2 gate (area optimization)

Date: 2026-11-26. Verdict: **original RTL retained.** `opt/best/exp_lut.v` is byte-identical to
`snapshot/exp_lut.v` (sha `873546cc`), and the golden passes the frozen contract
`d01fc4b8eb4f0492`.

Agent 3 ran concurrently under S1, with no access to `verif/` or `review/`
(`opt/OPTIMIZATION.md`, `opt/attempts.json`):
- 11 formulations, 138 texts. Each is EQY-proven equivalent at REGISTERED=0 and 1 and passes
  `test/blocks`; the negative controls fail.
- The in-context cone of the golden is 2,447.6 µm² (96 cells).
- Shipped-flow noise band: [41,063.4, 41,375.1] µm².
- No candidate shrinks the in-context cone:
  - the best family, c10, is −8.7 µm² at best;
  - its low chip samples come from ABC reshuffling the rest of the chip.
- Standalone savings (c08 −568, c10 −312 µm²) survive only behind a kept synthesis boundary.
  Both chip architects measured that a kept boundary costs more than it saves (c08 kept: −57.1,
  inconclusive), so flat synthesis stays (`pd_flow/chip_partition_DECISION.md`).

The physical design of exp_lut is part of the datapath cluster (D7).
