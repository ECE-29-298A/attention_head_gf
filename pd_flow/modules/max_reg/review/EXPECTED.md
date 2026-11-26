# max_reg: expected behaviour (Agent 2, derived before reading Agent 1's artifacts)

Sources read for this file: `pd_flow/baseline/original_rtl/max_reg.v`, the instantiation and FSM in
`pd_flow/baseline/original_rtl/attention_controller.sv`, the header of `mac_unit.v` (score
range), and `pd_flow/PHASE0_AUDIT.md`. Nothing under `pd_flow/modules/max_reg/verif/` was read
before this file was written.

## Interface

| Port | Dir | Width | Meaning |
|---|---|---|---|
| clk | in | 1 | single clock, rising edge |
| first | in | 1 | "this is the first score of the query" (load unconditionally) |
| en | in | 1 | a finished score is on S_in this cycle |
| S_in | in | signed 22 | score |
| M | out | signed 22 | running maximum (registered) |

No reset port. No other outputs. No parameters.

## Requirements (block contract, over the full input domain)

Notation: `M'` is M after the rising edge, `M` before it; all comparisons are two's-complement
signed 22-bit.

- **R1 load on first:** `en && first` -> `M' = S_in`, regardless of M (overrides the compare).
- **R2 signed greater:** `en && !first && $signed(S_in) > $signed(M)` -> `M' = S_in`.
- **R3 tie holds:** `en && !first && S_in == M` -> `M' = M` (bitwise; a tie is not a load, but a
  tie-load would also give `M' = M`, so R3 is observationally the same as "hold". A mutant that
  uses `>=` is therefore **observationally equivalent** at the port level. The contract can
  only distinguish it structurally, e.g. by flop enable activity, which is not a port property.)
- **R4 signed smaller holds:** `en && !first && $signed(S_in) < $signed(M)` -> `M' = M`.
- **R5 disabled holds:** `!en` -> `M' = M` for every value of `first` and `S_in` (`first` alone
  must never load; in context `first = token == 0` stays high for whole score rows).
- **R6 sign handling:** the compare is signed over all 22 bits: e.g. S_in = -1 vs M = 0 holds;
  S_in = 0 vs M = -1 loads; S_in = 2^21-1 vs M = -2^21 loads; S_in = -2^21 vs M = 2^21-1 holds.
  Unsigned compare, 21-bit compare, or sign-bit-only faults must be caught. Corner pairs:
  {-2^21, -1, 0, 1, 2^21-1}, the adjacent pairs (x, x+1), (x, x-1), and the in-context extremes
  2^20 and -1,040,384.
- **R7 width / all bits:** M' takes all 22 bits of S_in on a load (no stuck, swapped or dropped
  bits); a hold keeps all 22 bits.
- **R8 registered output (timing):** M changes only at a rising clk edge. There is no
  combinational path from clk-domain inputs (first, en, S_in) to M; M is the Q of 22 flops.
  Within a cycle M is constant whatever the inputs do. Load is visible one cycle after en (the
  next cycle's M), not in the same cycle and not two cycles later. No latch, no negedge flop,
  no gated or derived clock unless explicitly reviewed (see below).
- **R9 no reset / power-up independence:** M has an arbitrary power-up value. After the first
  `en && first`, the behaviour (M sequence) must be identical for every power-up value: i.e.
  for two copies started from different arbitrary states and fed the same inputs, M agrees
  from the cycle after the first `en && first` onwards. Before that first load M is
  unspecified; the contract must not assert anything about it (no init assumption in the
  DUT).
- **R10 sequence:** over any sequence with one `first` load followed by `en` pulses, M equals
  the signed maximum of all S_in values taken with `en` since (and including) the last
  `en && first`. This is the end-to-end usage property; it follows from R1-R5 by induction but
  should be checked once directly (a reference max over a sequence).
- **R11 interface:** exactly these ports, widths and signedness; module name `max_reg`; no
  extra ports (no rst, no clock enable added).

## Added reset: is it a violation?

An added synchronous or asynchronous reset needs a reset port. The interface has none, so an
added *port* is an interface violation (R11). An internal power-up init (`initial M = 0`, or a
reset driven by an internal power-on circuit) does not change any observable behaviour after
the first load (R9), and before the first load M is unspecified, so it is **not** a behavioural
violation; it is a synthesis issue (initial values are not synthesizable for ASIC, and Yosys
drops or rejects them in the GF180 flow). A mutant that resets M on some *existing* input (for
example `if (first && !en) M <= 0`) is a real violation of R5.

## Usage invariants (from attention_controller, for in-context reasoning only)

The block contract above must hold without these. They define the reachable domain, which
decides whether a surviving mutant is a real gap or only equivalent in context.

- U1 `en = score_done && !second_pass`. `score_done` is a one-cycle pulse at the end of each
  score row (pos wraps), reset to 0. So `en` is a 1-cycle pulse at least 1024 clocks apart.
- U2 `first = token == 0`. Within pass 1 the first `en` of every fresh run has token == 0, so
  each fresh run starts with `en && first`. `first` is high for many cycles with `en = 0`
  (whole first row, IDLE after reset); R5 matters in context.
- U3 After the last pass-1 score, token wraps to 0 and second_pass = 1, so `en = 0` for the
  whole of pass 2 and for every continue run (`second_pass <= cont`). M must hold for the
  whole of pass 2 (it is the M that mac_unit preloads per row, so any drift corrupts D = M - S).
- U4 A continue run before any fresh run reads garbage (documented); M is then the power-up
  value, which is allowed (R9).
- U5 Reachable S_in range: 64 products of INT8 x INT8, so S_in is in
  [-64*127*128, 64*128*128] = [-1,040,384, +1,048,576]. 2^20 is reachable (all Q = K = -128),
  so bit 20 of a positive score can be 1 with bit 21 = 0: a 21-bit compare is wrong even in
  context. Bits 21 and 20 are not both redundant.
- U6 Power-up: M is not reset. With `rst_n` low, score_done = 0 so en = 0: M holds its power-up
  value through reset.

## What a complete contract must cover

1. A golden reference written independently of the RTL (different construct: e.g. Python
   integer arithmetic for simulation; a separate SV expression with explicit `$signed` for
   formal), not a copy of the RTL expression.
2. R1-R7 as single-step properties proven for all 2^44 (S_in, M) pairs x {en, first}: unbounded
   formal (1-step induction suffices, since the property relates M to $past values) and
   simulation with directed corners from R6 plus random.
3. R8 checked structurally (22 flops of the expected type, all clocked by `clk` on the rising
   edge, no latches, no combinational path to M) *and* behaviourally (M stable within a cycle,
   one-cycle latency).
4. R9 checked by a two-copy (miter) proof from arbitrary, unconstrained initial state, or by
   showing that the per-step property implies it. No `initial` or init assumption on the DUT's M.
5. R10 sequence check against a reference max, in simulation at least.
6. Cover/vacuity: witnesses that each branch is reachable under the assumptions (first load,
   greater-load, tie, smaller-hold, !en hold, negative/positive crossing).
7. Assumptions: none on S_in, M, en, first for the block proof. Any assumption must be listed
   and justified; an in-context range assumption (U5) would be an overconstraint for the block
   contract.
8. The same contract re-run on the mapped GF180 netlist (gate level), formal and simulation,
   with the flop models known to match the Liberty function.
9. Honest result labels (proven (unbounded) only for a completed induction / SAT equivalence).

## Clock gating

R8 excludes a gated clock by default because:
- the contract proves behaviour at the port level of a single-clock design; a gated clock
  moves correctness into glitch-freedom and skew, which RTL formal does not see;
- a hand-made gate (`clk & en`) glitches and is a real bug; only an integrated clock-gating
  cell (ICG, latch-based) is safe, and its timing (setup of enable to the latch, clock skew to
  the gated flops) must be signed off by STA.

An ICG is a plausible power optimisation here (22 flops idle for all of pass 2 and most of
pass 1; `en` is active 1 cycle in 1024). A reviewed extension should allow exactly: the PDK
ICG cell (`gf180mcu_fd_sc_mcu7t5v0__icgtp_*`) driven by `clk` and an enable that is a
function of (en, first, S_in, M) that is 1 whenever a load is needed; formal on the netlist
with the ICG modelled by its Liberty function (latch + AND); a check that the enable is
implied by the RTL load condition (`load_rtl -> gate_en`); and STA clock-gating setup/hold
checks in signoff.
