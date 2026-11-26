# ripple_add: Phase 2 gate (area optimization)

Date: 2026-11-26. Verdict: **original RTL retained** (`opt/best/ripple_add.v` is byte-identical
to the golden file, SHA-256 `5977cad9…`). No RTL change, so the contract, EQY and timing are
trivially preserved.

Agent 3 (`opt/OPTIMIZATION.md`, `opt/attempts.json`) evaluated 17 hand-written candidates and
240 operand-order variants. Every candidate is EQY-proven equivalent to the golden at N=12 and
N=22, and all but two pass the frozen contract (c02 and c06 fail lint on unused bits). The best
module-level saving is about 55 µm² (behavioural `a+b+cin`, c01), at +12 to 13% adder delay.
Everything smaller than the original is slower: the original sits on the area/delay front.

## Orchestrator check: shipped-flow synthesis reverses the top-level numbers

Agent 3's top-level areas used `scripts/synth_area.py` (Yosys 0.71, default ABC). The chip is
built by LibreLane 3.0.14 (Yosys 0.62, `SYNTH_STRATEGY` AREA 2). Re-measured with
`scripts/ll_synth.sh` (the LibreLane run up to and including Yosys.Synthesis, project config
unchanged):

| Variant | synth_area.py top µm² | LibreLane synthesis top µm² |
|---|---:|---:|
| original | 42,145.6448 | **41,116.0960** (1,434 cells; equals the baseline harden) |
| n04_swap_or (OR operands swapped) | 40,995.36 (−1,150) | 41,201.7088 (+85.6) |
| c01 behavioural `a+b+cin` | 41,138.05 (−1,008) | 42,308.0896 (**+1,192**) |
| n03_swap_sum (XOR operands swapped) | 42,145.6448 (0) | 41,100.7296 (−15.4) |

The default-ABC recipe does not predict shipped area at top level; for c01 it gets the sign
wrong. c01 is rejected on shipped area as well as timing. Evidence: `opt/shipped_flow/*.stat.json`.

## Method change for all later modules

Phase 2 acceptance now requires a lower **shipped-flow top-level area** (`ll_synth.sh`), not
just a lower `synth_area.py` area. Module-level `synth_area.py` numbers stay useful for
exploration only. Cell-level structuring (addf chains) is deferred to Phase 3:
Agent 3's probe found addf_1 chains at −25.8% (N=22) / −24.3% (N=12) area, but about +90% carry
delay (+20 ns at SS for N=22). That has to be checked against the +41.79 ns chip slack.
