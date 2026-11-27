# mac_unit: expected behaviour (Agent 2, written before reading `verif/`)

Source: `snapshot/mac_unit.v` (SHA-256 `221110a1…`), `ripple_add.v`, `attention_controller.sv` (the only
instantiation, `OUTPUTS = 8`, so `P = 3`, `sel` is 3 bits, the ring is 160 bits). No reset, no `initial`,
no enable on the ring. Every register has a free power-up value.

Notation: `sx(n, v)` = sign-extend v to n bits; `+`/`-` wrap modulo 2^width; `b = bit_sel` (0..7),
`top = (b == 7)`; ring element `R[k] = ring[20k+19 : 20k]`, k = 0..7, `O0 = R[0]`.

## R1. Outputs
- `O0 = R[0]` (combinational from the ring, no logic). `S` and `L` are the registers themselves.

## R2. Shared adder (combinational, one 22-bit adder)
- Operand `x` (9 bits): `accum_mode ? {0, W}` (W **unsigned**) `: sx(9, qi)` (qi **signed**).
- Bit: `bit_on = accum_mode ? (accum_en & v[b]) : ki[b]`.
- Term: `T = bit_on ? (sx(22, x) << b) : 0` (22-bit, no truncation: |x| < 2^9, b <= 7).
- Sign: `neg = accum_mode ? (accum_en & top) : (top ^ subtract)`. Bit 7 is the two's-complement sign
  bit of the serial operand (v or ki), so its weight is -2^7. In score pass 2 (`subtract = 1`) the
  whole product is negated, so bits 0..6 subtract and bit 7 adds.
- Base: `A = accum_mode ? (load_o ? 0 : sx(22, O0)) : S`, with `load_o = accum_en & first & top`.
- `sum = neg ? A - T : A + T` (mod 2^22). `sum[21:20]` is unused in accumulate mode.

## R3. S register (22-bit signed)
- `load` has priority: `S' = subtract ? M : 0`.
- else `score_en`: `S' = sum` (whatever mode, i.e. also `accum_mode = 1` gives the accumulate sum
  widened to 22 bits; never exercised by the controller, but it is the module's port behaviour).
- else hold.
- Score semantics (accum_mode = 0, controller: one ki bit per score_en cycle, MSB first, all 8 bits
  of one K byte with the same qi): one byte adds `qi*ki` (pass 1) or subtracts it (pass 2).
  Over a 64-dimension row: pass 1 `S = Σ q·k`; pass 2 `S = M - Σ q·k = D`.
  Range: |Σ q·k| <= 64·2^14 = 2^20; `M - S` <= 2^20 + 64·128·127 < 2^21: no overflow in 22 bits.

## R4. Ring (8 × 20 bits, rotates every clock, both modes)
- `R[k]' = R[k+1]` for k = 0..6, `R[7]' = H`, where
  - `H = sum[19:0]` when `accum_mode = 1`,
  - `H = O0` (head unchanged, the adder is bypassed) when `accum_mode = 0`.
- Hence with `accum_en = 0` (in either mode) the ring is a pure rotation of period 8: the 8 values are
  preserved, and O0 returns to the same value after 8 clocks.
- Accumulate (`accum_mode = 1, accum_en = 1`):
  - `load_o` (first & top): `H = (v[7] ? -(W << 7) : 0)` (fresh load; old head discarded).
  - top, not first: `H = O0 - (v[7] ? W << 7 : 0)`.
  - otherwise: `H = O0 + (v[b] ? W << b : 0)`.
  - all mod 2^20. Over the 8 bits of one V byte (MSB first) for one component: `O += W·v` (v signed),
    and the first token starts from 0: after all tokens `O = Σ_t W_t · v_t`.
  - `first` without `top` does **not** clear (only the bit-7 cycle of token 0 loads).
  - `accum_en = 1` with `accum_mode = 0` has no effect on the ring or on the adder sign (bypass).
- Range: |O| <= 16·255·128 = 522240 < 2^19: fits 20-bit signed.

## R5. L register (12 bits, unsigned weight sum)
- Updates only when `accum_en & (sel == 0) & (b == 0)`: `L' = (first ? 0 : L) + W` (mod 2^12),
  through a separate 12-bit adder (independent of accum_mode, of v, of the main adder).
- Otherwise hold. Controller: once per V block (component 0, bit 0), so `L = Σ_t W_t` (<= 16·255 = 4080).

## R6. Controller-driven domain (OUTPUTS = 8)
- accum_mode = (state != SCORE); score_en and load only in SCORE; accum_en only in VALUE.
  So in the chip `score_en -> !accum_mode`, `load -> !accum_mode`, `accum_en -> accum_mode`.
- SCORE: `bit_sel = ~pos[2:0]`, `ki = {8{bit}}`, `load` at pos 0..7 (score_en = 0 there), subtract =
  second_pass, M from max_reg.
- VALUE: `sel = pos[2:0]`, `bit_sel = ~pos[5:3]`, `v = {8{bit}}`, `first = (token == 0)`.
  The tape gives c0 b7, c1 b7, … c7 b0; the head holds component pos[2:0] since the ring turns every
  clock and pos only counts or wraps at a multiple of 8 between the first V bit and the last divide.
- Divider reads `O0` in DIV_START at `pos[2:0] == output_index` (ring must keep rotating, unmodified,
  outside VALUE). exp_lut reads `S` combinationally (D = M - S) during VALUE.

## R7. Edge cases the contract must cover
- E1 W = 255, v = -128 (bit 7 only), first: O = -32640; W = 255, v = 127; W = 0; v = -1.
- E2 qi = -128, ki = -128 (product +16384); qi = -128, ki = 127; qi = 127, ki = -128; ki = 0.
- E3 S near ±2^21 (wrap mod 2^22), O0 near ±2^19 (wrap mod 2^20, sign extension of O0 into a).
- E4 `load` and `score_en` together (load wins), `load` with subtract (S = M, including M negative).
- E5 `first` with b != 7 (no load), `first` with accum_en = 0 (no load, no L clear).
- E6 L: `sel != 0` or `b != 0` holds; first clears; 12-bit wrap (4095 + 1 = 0).
- E7 accum_mode = 0 while accum_en = 1: ring bypass (head unchanged), L still updates (R5).
- E8 accum_mode = 1 with score_en = 1: S takes the accumulate sum (out of chip domain, port
  behaviour).

## R8. Power-up / reset
- **No reset and no initial value anywhere.** Every register (S, L, 160 ring bits) powers up free.
  The chip relies on this: S is loaded at pos 0 of every score row, the ring head is loaded on token 0
  bit 7, L is loaded on token 0 (first). A candidate must not add a reset, an init value, a clear, or an
  enable that changes behaviour from an arbitrary state; since there is no reset to anchor to,
  equivalence must hold from **every** matched start state (for all 2^194 states), not only from a
  reachable one.
- Adding an `initial`/reset is an interface/power-up behaviour change and must be killed (a reset
  input would also change ports).

## R9. Structural
- Ports and widths exactly as in the golden, parameter `OUTPUTS` (default 8; 2, 4 or 8 allowed).
- Positive-edge D flops only, no latches, no async set/reset, no memories.
