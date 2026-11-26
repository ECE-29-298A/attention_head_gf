# max_reg: Phase 2 gate (area optimization)

Date: 2026-11-26. Verdict: **original RTL retained** (`opt/best/max_reg.v` is byte-identical to
the golden).

Agent 3 (`opt/OPTIMIZATION.md`, `opt/attempts.json`): 14 candidates, each lint-clean, EQY-proven
equivalent to the golden (sat, 22 M flops matched, no assumptions, cutpoints or black boxes),
and 17/17 on the frozen contract.

## Shipped-flow noise band (golden rewrites through `ll_synth.sh`)
The band is [41,063.4, 41,351.0] µm², i.e. −52.7 / +234.9 around the base (41,116.1). Candidate
rewrites swing up to +806. `opt/cone.py` separates the in-context max_reg cells from the rest of
the chip.

## Best candidate: c10 (majority-ripple compare, tie as don't-care)
Shipped-flow synthesis: 40,936.1 µm² (−180 against the base), 81 to 127 µm² below the lowest
golden sample. Full harden (`/Users/samuelzhang/ttharden/mr_c10v4`), checked by the
orchestrator against the raw `metrics.json`:

| | Baseline | c10_clean |
|---|---:|---:|
| Std-cell area | 46,819.2 µm² | 47,073.9 µm² (+254.7, inside the harden noise spread) |
| ss setup WNS | 41.79 ns | 40.23 ns |
| Slew / cap / fanout | 381/1/11 | 269/1/11 |
| Power (vectorless) | 3.050 mW | 3.365 mW (+10.3%, outside the noise spread) |
| DRC / LVS | clean | clean |

Logic shrank 149 µm², but repair added buffers (+241), delay cells (+141) and clock buffers
(+75). **Rejected**: no confirmed area gain, and higher power.

## Findings carried forward
- The reviewer's module-level −272 µm² for `>=` is default-ABC noise; a plain operand swap of
  the golden moves it by −296.
- The realistic gain is about 150 to 250 µm² of logic (about 0.5% of the chip), below the about
  400 µm² harden noise. A single harden cannot confirm a gain below about 400 µm².
- Removing flops: the controller's score range allows dropping M[21] and rebuilding it, but the
  rebuild costs more (+241.5 chip). Sharing the compare with the mac adder changes interfaces
  and is probably a net loss. Clock gating is out of scope until the contract is extended.
