# Zero max-cap violations (user decision D13): flow-config experiments, 2026-11-26

Netlist: wc_ref4, which is c06 + c09 + controller a11 with the x0 config. All runs are full hardens in
`/Users/samuelzhang/ttharden/<run>`. Area is `design__instance__area__stdcell`.

| Run | Change vs wc_ref4 | Std-cell µm² | Slew/cap/fanout | Setup / hold (ns) | DRC/LVS/antenna |
|---|---|---:|---|---|---|
| wc_ref4 | none | 43,151.0 | 148/**2**/0 | 39.36 / 0.094 | 0/0/0 |
| wc_cap_a | RUN_POST_GRT_DESIGN_REPAIR true | 43,309.1 | 80/**1**/0 | 39.97 / 0.088 | 0/0/0 |
| wc_cap_b | DESIGN_REPAIR_MAX_CAP_PCT 25 | 43,208.1 | 134/**1**/0 | 39.25 / 0.090 | 0/0/0 |
| wc_fo16 | MAX_FANOUT_CONSTRAINT 16 | 43,203.7 | 152/**1**/0 | 39.63 / 0.102 | 0/0/0 |
| wc_fo18 | MAX_FANOUT_CONSTRAINT 18 | 43,188.4 | 152/**1**/0 | 39.48 / 0.079 | 0/0/0 |
| wc_cap_e | DESIGN_REPAIR_MAX_WIRE_LENGTH 300 | 43,181.8 | 163/**2**/0 | 39.38 / 0.092 | 0/0/0 |
| **wc_cap_f** | **MAX_WIRE_LENGTH 300 + MAX_FANOUT 16** | **43,295.9 (+144.9)** | **124/0/0** | 39.53 / 0.099 | 0/0/0 |

## Mechanism
- Every violator is a post-GPL fanout-split `buf_3` (lib max_cap 1.062 pF) driving a broadcast mux-select net.
- The 0.2 pF limit is the design-wide `MAX_CAPACITANCE_CONSTRAINT`, so **upsizing the driver cannot fix it**.
- At fanout 20 the 20 `mux2` S pins alone are about 0.20 pF.
- At fanout 16 the pins are 0.099 pF and the rest is about 0.106 pF of wire, from sinks spread about 600 µm apart.
- Only the combination of a fanout cap and wire-length buffering removes every violator.

## Recommendation
Config **F3**, the cheapest measured setting that gives zero:
- `MAX_FANOUT_CONSTRAINT` 20 → 16;
- `DESIGN_REPAIR_MAX_WIRE_LENGTH` 0 → 300.

The cap margin at the closest pin is not reported. Cap = 0 is re-checked at the final signoff harden.
