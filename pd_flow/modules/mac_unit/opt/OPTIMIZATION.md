# mac_unit: architectural area optimization (Agent 3, provisional)

Date: 2026-11-26. **Recommendation: c09 (`opt/best/mac_unit.v`, SHA-256 `e94ddd13…`).**
- It is EQY-proven equivalent to the golden at OUTPUTS = 8, 4 and 2, with no assumptions and no caller guarantee.
- It keeps every flop (ring, S and L, by name), so no lemma file is needed.
- Lint is pass-static: the only warning is the golden's own `ripple_add c[22]` UNUSEDSIGNAL.
- All existing tests pass.

It saves **−276.6 µm²** on chip synthesis with the original RTL. With the accepted divider c06 in place it saves **−726.6 µm²**. The in-context mac cone shrinks by −349 / −531 µm².

The gain is real but small next to ABC's text noise. The paired median is −224 (original) and −391 (c06). In each context, 6 of 7 paired texts are negative.

Everything here is provisional: the frozen contract does not exist yet, and `verif/` and `review/` were not read.

## Flow and measurement
- **Synthesis flow:** `ll_synth_x0.sh` is a copy of the divider's private script (shipping x0 config, md_x0_full). The golden reproduces 40,725.3504 µm², 1,380 cells, netlist `99daa702` bit for bit.
- **Ship script:** `ship.sh` swaps only `mac_unit.v`, runs one job at a time and waits while 2 or more containers are up. Each run takes about 8 s.
  - `CTX=c06` uses `base_c06/` (original_rtl plus the accepted divider c06 `9e6530df`). Golden in that context: 40,358.752 µm², netlist `3a58fe17`.
  - c06 is the context the chip will actually ship, so it is the more relevant one.
- **Cone split:** `cone.py` gives the in-context cone using the attrib.py rule.
  - MAC flops are S (alias `exponent_unit.D`), the ring (`mac.ring`, `divider_unit.sum_in`, `magnitude[0]`) and L (`divider_unit.denominator`), 194 in total.
  - A combinational cell belongs to MAC when its DEST is {MAC}.
  - exp_lut's table (cells whose SRC is only S and score_shift) is split out as `exp`.
  - Golden cone: 603 cells, 20,000.5 µm² = flops 12,350.2 + logic 7,650.3.
  - The mac/exp boundary moves with ABC, because W feeds only the MAC. Read mac and mac+exp together.

## Noise band (golden structural rewrites)
Many cosmetic rewrites collapse to the golden netlist in Yosys: v1–v6, n3, n8, n9 and n12. n11 gives the same netlist as n2. The distinct ones are below. n5 is excluded from the band because it introduces a `$mul`.

| text | orig chip | orig mac | c06 chip | c06 mac |
|---|---:|---:|---:|---:|
| base | 40,725.4 | 20,000.5 | 40,358.8 | 20,259.5 |
| n1 a-mux AND-OR | 40,573.9 | 19,794.1 | 40,185.3 | 20,108.0 |
| n2 ring tail XOR | 40,980.0 | 19,873.1 | 40,161.2 | 19,912.7 |
| n4 bit-select mask | 40,872.4 | 19,914.9 | 40,022.9 | 19,965.3 |
| n6 neg SOP | 40,659.5 | 19,822.7 | 40,407.0 | 20,145.4 |
| n7 x-mux AND-OR | 41,017.3 | 19,873.1 | 40,358.8 (= base) | 20,259.5 |
| n10 neg XOR | 40,909.7 | 19,982.9 | 40,227.0 | 20,160.7 |
| (n5 multiply, excluded) | 41,667.1 | 20,472.4 | 40,582.7 | 20,389.0 |

**Bands:**
- **Original context:** chip [40,573.9, 41,017.3], mac [19,794.1, 20,000.5].
- **c06 context:** chip [40,022.9, 40,407.0], mac [19,912.7, 20,259.5].

## Candidates (base text; Δ against the golden in the same context)
| # | change | orig chip Δ | orig mac Δ | c06 chip Δ | c06 mac Δ | decision |
|---|---|---:|---:|---:|---:|---|
| c01 | invert the 9-bit multiplicand before the shift; low bits filled with neg by an OR mask | +250.3 | +28.5 | — | — | rejected |
| c01b | same inversion; neg fill by a right shift of {sext(xn), 7{neg}} by 7−bit_sel | +182.2 | −87.8 | −467.6 | −518.1 | component of c09 |
| c02 | negate the multiplicand before the shift (valid because x ∈ [−128, 255]); cin = 0 | +195.4 | +90.0 | — | — | rejected |
| c03a/b/c | `+` in place of ripple_add (main / L / both) | +869 / +233 / +1,278 | | — | — | rejected |
| c04 | L_next = first ? W : L+W (mux after the adder) | −39.5 | −85.6 | −74.6 | −390.7 | component of c09 |
| c05 | S update as one enable | 0 (same netlist) | | | | — |
| c06 | gate the multiplicand with bit_on before the shift | +81.2 | −22.0 | — | — | rejected |
| c07 / c08 | gate and invert (c07); c06 + c04 (c08) | +283.2 / +54.9 | | — | — | rejected |
| **c09** | **c01b + c04** | **−276.6** | **−349.0** | **−726.6** | **−531.2** | **recommended** |
| c10 | c07 + c04 | +96.6 | −116.3 | −680.5 | −601.5 | not robust (orig +) |
| c11 / c12 | c01 + c04 / c02 + c04 | +90.0 / −112.0 | | +783.7 / +256.8 | | rejected |
| c13 | c01b + L as `+` | −223.9 | −184.4 | −366.6 | −546.6 | below c09 |
| c14 | c09 with the multiplicand built per mode | −432.5 | −265.6 | −395.1 | −566.4 | rewrites +924 / +490 (orig) → rejected |

**Paired c09 − golden per text:**

| text | orig | c06 |
|---|---:|---:|
| base | −276.6 | −726.6 |
| n1 | −136.1 | +239.3 |
| n2 | +757.3 | −107.6 |
| n4 | −423.6 | −390.8 |
| n6 | −223.9 | −592.7 |
| n7 | −568.5 | −726.6 |
| n10 | −129.5 | −377.6 |
| **median** | **−223.9** | **−390.8** |

The shipped c09 text sits below the golden band in both contexts, for chip and for mac. The n2 (orig) and n1 (c06) outliers show that a later context change can erase the gain. Re-measure c09 after any other module changes. Keep the shipped text byte-exact, including line numbers: Yosys auto-names carry line numbers, and that is enough to move ABC.

**Class breakdown.** Sequential area is unchanged (20,944.4 orig / 20,498.8 c06; 194 MAC flops). The whole gain is combinational.

In the cone, xnor2+xnor3+xor3 drop from 19 to 8 cells in the original context, and from 21 to 15 in c06.

**Where the gain comes from.** The golden XORs the 22-bit shifted term with neg. c09 XORs the 9-bit multiplicand before the shift, and the shifter fills the vacated low bits with neg. Expressing that fill as a right shift of a 29-bit word is what lets ABC map it well; the OR-mask form, c01, does not.

## Ideas evaluated and not pursued
**Widths: no narrowing is possible.**

| register | bound | needs |
|---|---|---|
| O | [−16·255·128, 16·255·127] = [−522,240, 518,160] | 20-bit signed |
| S, pass 1 | [−64·128·127, 64·128·128]; the max is exactly 2^20 | 22 bits |
| S, pass 2 | M − partial sums ∈ ±2,088,960 | 22 bits |
| L | ≤ 16·255 = 4,080 | 12 bits |

**Sharing the L adder with the main adder: impossible.** L updates on an accum_en cycle, and every VALUE cycle uses the main adder for the ring head. W is valid only during VALUE. Only the adder's top 2 bits are free in accumulate mode.

**Cost probes (c06 context, non-equivalent, `probes/`).** Each probe removes one piece of logic; its Δ chip is the most that removing that piece could save.

| piece removed | Δ chip µm² |
|---|---:|
| L adder (incl. 4 constant flops) | −1,787 |
| x mux | −1,297 |
| barrel shifter | −858 |
| ring tail mux | −676 |
| S hold mux | −601 |
| load_o | −393 |
| L first-gating | −176 |

Every one of these is functionally required for unconditional port equivalence.

**Caller-dependent rewrites: not adopted.** Examples are using load ⇒ !accum_mode ∧ !score_en, or the ki = v = {8{nibble[3]}} replication. Flat synthesis already sees the combinational ones. The sequential ones, such as a serial L or a Horner-style S, change per-cycle port values.

**Latch register-file ring: rejected by analytical estimate (not run).** A rotating ring with a fixed head needs a pointer, write gating and a 20 × 8:1 read mux.

| ring | estimate |
|---|---:|
| latch register file: 160 latq_1 + 8 ICG + about 3,400 µm² read mux + pointer | ≈ 11,200 µm² |
| current: 160 dffq_1 + tail mux | 10,756 µm² |

## Proposals for the orchestrator (cell-kind changes; measured at synthesis, c06 context; not adopted)
- **g1 = c09 + icgtp_1 clock gates on S (E = load|score_en) and L (E = L enable), hold muxes removed.**
  - Chip 39,428.0, which is −930.8 vs golden and **−204 vs c09**.
  - It is port-equivalent under any input sequence.
  - It needs the gated-clock contract extension.
  - CTS cost is not measured.
- **g2 = g1 + ring clock-gated off while accum_mode = 0, tail mux removed.**
  - Chip 38,837.5, which is −1,521 vs golden and **−795 vs c09**.
  - It also stops the 160 ring flops toggling during SCORE, a power win.
  - It is **caller-dependent**: O0 is frozen during SCORE instead of rotating. Ring phase is preserved only because every SCORE stay lasts exactly 1,024 cycles, which is ≡ 0 mod OUTPUTS (pos enters SCORE at 0 and leaves at &pos). The divider reads o0 only at DIV_START.
  - It needs a controller-level check as well as the gated-clock contract.

## Verification of c09 (labels per AGENT_CONTEXT)
- **EQY at OUTPUTS = 8, 4 and 2: proven (unbounded).** `eqy_O.eqy.in`, flattened, SAT depth 1. ring, S, L and the ports are matched by name; internal combinational nets are nomatched. Result: PASS, 24/24 partitions. The golden against itself also passes.
- **Negative controls (`negctl/y01..y04`), all FAIL at all three OUTPUTS:**
  - y01: zero fill;
  - y02: L mux swapped;
  - y03: cin = 0;
  - y04: zero fill when bit_on = 0.
- **Lint: pass-static.** Verilator -Wall at 8, 4 and 2 gives one warning, identical to the golden's.
- **Tests: pass-sampled**, unmodified, on a temp repo copy: blocks mac_unit at 8, 4 and 2, controller (8, 4, 2), top, and test/ make.
- **Timing: not measured** (no harden). The logic depth is essentially the golden's: the XOR moves ahead of the shifter. Baseline ss slack is +41.8 ns.
- **No added reset or init.** Power-up behaviour is unchanged, because the flops are the same.

## Files
- **Scripts:**
  - `make_cands.py`, `make_paired.py`: exact, asserted substitutions;
  - `ship.sh`, `ll_synth_x0.sh`, `cone.py`: flow and cone split;
  - `verify.sh`, `eqy_O.eqy.in`: verification;
  - `collect.py` plus `descriptions.json` → `attempts.json` (105 rows).
- **RTL:** `candidates/`, `variants/`, `probes/`, `proposals/`, `negctl/`, `base_c06/`.
- **Results:** `shipped_flow/` (stat, netlist, cone json per run) and `runs/` (RTL copies, EQY logs, test logs, `verify_main.txt`).
