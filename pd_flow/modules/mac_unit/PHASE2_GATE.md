# mac_unit: Phase 2 gate (area optimization)

Date: 2026-11-26. Verdict: **c09 ACCEPTED.** RTL `opt/best/mac_unit.v`, sha256 `e94ddd1363b3e01b…`.

**What c09 changes:**
- The negate XOR is applied to the 9-bit multiplicand before the shift. The vacated low bits are filled with
  `neg` by right-shifting `{sext(xn), 7{neg}}` by `7 − bit_sel`.
- `L_next = first ? W : L + W`, so the `first` mux comes after the L adder.
- No flop changes: ring, S and L keep their names. No reset or init. No caller guarantee is used.

**Frozen contract** (orchestrator runs): RTL 24/24 (OUTPUTS 8/4/2, `eqy_rtl` and `seq_eq` proven); gate (8, contract
recipe) 13/13. Tests pass unmodified (Agent 3).

**Area at signoff** (full hardens, orchestrator-checked):
- **wc_ref2** (c06 + c09): **43,429.8 µm²**, against wc_ref (c06 only) at 44,777.7, so **−1,347.9**.
  - Upsizing fell from about 800 to 289.8.
  - Slew/cap/fanout 146/1/0, setup +39.42, hold +0.081, DRC/LVS/antenna 0.
- **Cumulative:** −3,389.4 µm² (−7.2%) against the 46,819.2 baseline.
- The synthesis estimate was −727 with c06 (`opt/OPTIMIZATION.md`).

**Rejected proposals.** Clock gating (D12 / D12b) was measured at signoff and lost:
- g2: +1,016.4 µm²;
- g1: +897.9 µm²;
- in both cases because of the extra clock trees and dummy loads.
