# divider: expected behaviour (Agent 2, written before reading `verif/`)

Sources: `snapshot/divider.v` (SHA-256 `a4943458…`), `snapshot/attention_controller.sv`
(`0cb0268f…`), `baseline/original_rtl/mac_unit.v` and `exp_lut.v` (for the caller domain),
`python/src/attention_model.py` `divide_round` and `reg_widths`. Notation: cycle `t` is the
interval before rising edge `t+1`; "accept at `t`" means `rst_n && start && !busy` in cycle `t`.

## R. Requirements

R1 Value function (valid request, either configuration). With `O = sum_in`, `L = denominator`
sampled at the accept cycle, `Z = 16·|O|`, `q, R = divmod(Z, L)`, `Q = q + (2R >= L)`:
`result = O < 0 ? -Q : Q` (12-bit two's complement). This is `divide_round(O, L, out_frac=4)`:
round to nearest, ties away from zero (the magnitude is rounded half up, then the sign applied).
A negative O that rounds to magnitude 0 gives `0x000` (there is no negative zero).
Multiplicative form (used by my reference, no division operator): with `r = result`,
`Q = |r|`, sign(r) consistent with sign(O) (r = 0 allowed for either), and
`(2Q-1)·L <= 32·|O| < (2Q+1)·L`. The intervals partition the line, so this fixes r uniquely.

R2 Range. Valid means `L >= 1`, `O != -524288`, and the rounded value fits in signed 12 bits:
`O >= 0: 32·O < 4095·L` (Q <= 2047); `O < 0: 32·|O| < 4097·L` (Q <= 2048, so -2048 is a valid
result). Note: the in-range condition alone already implies `L >= 1` (L = 0 is never in range)
and `O != -524288` (32·524288 = 16,777,216 > 4097·4095 = 16,777,215). So the three caller
guarantees of the header collapse to one: **the exactly rounded value is in range**.

R3 Invalid handling, `CHECK_INVALID = 1` (default): L = 0, O = -524288, or an out-of-range rounded
value completes with `result = 0`, `done` pulse, normal latency. Not saturation. Overflow
boundaries: positive `Q = 2047` valid / `2048` invalid; negative `Q = 2048` valid / `2049` invalid;
quotient >= 4096 invalid.

R4 `CHECK_INVALID = 0` (chip): no detection. Outside the valid domain the result is unspecified
(the RTL gives the low 12 bits of `±Q`; O = -524288 happens to give 0; L = 0 gives garbage). The
contract must state the domain as an assumption, not check behaviour there.

R5 `LATCH_DENOMINATOR = 1` (default): the divisor is sampled at accept (the RTL samples it every
IDLE cycle; the last one is the accept cycle). Later changes of `denominator` do not affect the
running division. `LATCH_DENOMINATOR = 0` (chip): `denominator` is used live during the 24 busy
cycles (DIVIDE and ROUND); the caller must hold it equal to its value at accept for those cycles.
`invalid_r` always samples `denominator` at accept (CHECK_INVALID = 1 only).

R6 `sum_in` is sampled only at the accept cycle (the chip's O0 is a rotating ring head that
changes every clock, so this matters). Values of `sum_in`, `denominator` (when latched) and `start`
outside the accept cycle are ignored.

## P. Cycle-level protocol

P1 Accept at `t`: `busy = 1` during cycles `t+1 .. t+24` (24 cycles: 23 DIVIDE with step 0..22,
then 1 ROUND); `busy` is combinational from the state (`state != IDLE`).
P2 `done = 1` exactly in cycle `t+25` (registered, one cycle), with the new `result` valid in the
same cycle; `busy = 0` in `t+25`. Latency accept-to-done = 25 cycles.
P3 Back to back: a start in the done cycle `t+25` is accepted (next done at `t+50`). Starts in
`t+1 .. t+24` are ignored entirely (no restart, no queuing, no effect on the running division).
P4 Result hold/shift: outside reset and completion, `result(t+1) = shift(t) ? {result[10:0],0} :
result(t)`. Shift works in every state (including busy, on the previous result). MSB first on
`result[11]`; zeros are shifted in. A completing division (ROUND edge) overrides a shift in the
same cycle.
P5 Reset: synchronous, active low, highest priority: `state = IDLE`, `done = 0`, `result = 0` on
the next cycle; aborts a running division (no done follows); beats start, shift and completion
in the same cycle. Datapath registers (`quotient`, `remainder_value`, `step`, `negative`,
`invalid_r`, `saved_divisor`) are not reset; they are reloaded every IDLE cycle, so behaviour
after one reset cycle is independent of the power-up state (P6).
P6 Power-up independence: from an arbitrary register state, after one cycle with `rst_n = 0`, all
outputs follow P1..P5 and R1. Unreachable state `2'd3` goes to IDLE (the default arm).
P7 `done` never pulses without a preceding accept 25 cycles earlier and no reset in between.

## C. Caller guarantees relied on by the chip configuration (LATCH_DENOMINATOR = 0, CHECK_INVALID = 0)

C1 In-range result (R2), which implies L >= 1 and O != -524288. In the chip: `O = Σ W_t·v_t`, `L =
Σ W_t` with `v_t` in [-128, 127], so `-128·L <= O <= 127·L`: Q <= 2048 for negative and <= 2032 for
positive (and 32·128·L = 4096·L < 4097·L). L <= 16·255 = 4080 fits. L >= 255 when the tape is
consistent (the maximum's token gives W = 255); with an inconsistent tape (for example cont = 1
before any fresh run) L can be 0, which is outside the divider's contract (system-level caveat,
not a divider bug).
C2 Denominator stable from accept through the ROUND cycle (cycles t .. t+24). In the chip,
`weight_sum` (mac_unit L) only changes when `accum_en` (VALUE state); the divider runs in
DIV_START/DIV_WAIT, so it is stable.
C3 Not required by the divider but true in the chip: start is a one-cycle pulse while idle, and
`shift` (= out_shift && out_valid) is only active in OUTPUT, when the divider is idle, so the
shift/done collision and start-while-busy never occur in context. A contract that only checks the
in-context subset would miss P3/P4 bugs; the block contract should check the full protocol.

How a contract should state these: as SBY `assume`s on the inputs (C1 at the accept cycle,
C2 while busy), conditioned on the configuration, with a cover/vacuity check that the domain is
non-empty and reaches done with the interesting values (ties, -2048, max L). Over-constraining
risks: assuming `-128·L <= O <= 127·L` (the chip domain, narrower than R2) is acceptable for the
chip but must be named as such; assuming `start` only when idle, or no `shift` while busy, or
`denominator` constant forever, would hide P3/P4/R5 bugs.

## E. Edge cases (value function)

E1 O = 0 (any L), O = ±1 with L in {1, 2, 31, 32, 33, 4095}.
E2 Exact ties `2R = L` (L even), positive and negative (must round away from zero), and the
neighbours `2R = L ± 1`. Example: O = 1, L = 32 gives 1; O = -1, L = 32 gives -1; O = 1,
L = 33 gives 0; O = -1, L = 31 gives -1.
E3 Range extremes: result 2047 (32·O = 4095·L - 1), -2048 (O = -128·L, chip extreme),
2032 (O = 127·L), the CHECK_INVALID = 1 boundaries 2047/2048 and -2048/-2049, quotient >= 4096,
rounding carry 4095 + 1.
E4 Divisor extremes: L = 1 (R = 0 always), L = 255 (chip minimum), L = 4080 (chip maximum),
L = 4095, L = 2048 and powers of two, L = 0 (CHECK_INVALID = 1 only).
E5 Dividend extremes: |O| = 522240 (chip maximum), O = 524287, O = -524287, O = -524288 (invalid),
O with bit 18 set (|O| >= 2^18) for both signs, since magnitude bit 18 and the sign bit are
adjacent.
E6 A negative O whose magnitude rounds to 0 (no negative zero), e.g. O = -1, L = 4095.
E7 Random spot checks over the valid domain for both configurations.

Because the result is produced by a 24-cycle sequential datapath, I treat the value function as
sequential behaviour under D9b: it needs an SBY property (k-induction or BMC covering a full
operation from an arbitrary accept), not only edge/spot simulation. Edge cases alone cannot show
the absence of a rare-value bug.

## M. Things a contract could miss (mutation targets)

Latency ±1; ties toward zero (both signs, or negative only); sign bit taken from the wrong bit;
negative result off by one (`~q + s` instead of `~q + !s`); start while busy restarting the
division; shift overriding completion; shift rotating instead of zero-filling; result or done not
cleared by reset; reset not aborting; remainder not cleared at load (history dependence);
`LATCH_DENOMINATOR = 1` sampling continuously (equals the 0 behaviour; only a test that changes
`denominator` while busy at LATCH = 1 catches it); default parameters changed; overflow comparison
off by one at -2048; a rare-value corruption at one interior point; busy dropping in ROUND.
