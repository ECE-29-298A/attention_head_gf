# exp_lut: expected behaviour (Agent 2, derived before reading Agent 1's artifacts)

Sources read for this file: `pd_flow/modules/exp_lut/snapshot/exp_lut.v` and
`attention_controller.sv` (SHA-256 checked against `snapshot/SHA256SUMS` and
`baseline/original_rtl/`), `src/mac_unit.v` (how W is consumed, score range),
`python/src/attention_model.py` (`exp_table`, `exp_weight`), `test/blocks/test_exp_lut.py` and
`test/blocks/Makefile`, `pd_flow/PHASE0_AUDIT.md`. Nothing under `pd_flow/modules/exp_lut/verif/`
or `opt/` was read before this file was written.

## Interface

| Port | Dir | Width | Meaning |
|---|---|---|---|
| parameter `REGISTERED` | | int | **default 1** (the block test `make exp_lut` instantiates the default); the chip uses 0 |
| clk | in | 1 | rising edge; used only when REGISTERED = 1 |
| rst_n | in | 1 | synchronous, active low; used only when REGISTERED = 1 |
| start | in | 1 | request; in the chip tied to `1'b0` |
| D | in | 22 | **unsigned** distance M − S |
| shift | in | 4 | 0..15 |
| done | out | 1 | |
| W | out | 8 | **unsigned** weight 0..255 |

Module name `exp_lut`. No other ports. The default value of `REGISTERED` is part of the interface
(changing it to 0 would silently change what `test/blocks` tests).

## The function

For `D` in `[0, 2^22)` and `s = shift` in `[0, 15]`:

- `D' = round_half_up(D / 2^s) = floor(D / 2^s + 1/2)`. For `s = 0` this is `D` (no rounding).
  For `s >= 1` it equals `(D + 2^(s-1)) >> s` without overflow (computed at full width).
- `W(D, s) = round(255 · e^(−D'/4))` if `D' <= 24`, else `0`.

Certified table (exact rational interval arithmetic, `review/ref/ref_exact.py`; no entry is an
exact half-integer, so the rounding mode of `round` does not matter, except the trivially exact
`D' = 0`):

| D' | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 | 24 | ≥25 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| W | 255 | 199 | 155 | 120 | 94 | 73 | 57 | 44 | 35 | 27 | 21 | 16 | 13 | 10 | 8 | 6 | 5 | 4 | 3 | 2 | 2 | 1 | 1 | 1 | 1 | 0 |

Near-tie entries (most likely to be got wrong by an alternative derivation, e.g. a float
table, truncation, or a different rounding): `D' = 25` (exact 0.49227 → **0**, margin 0.0077),
`D' = 8` (34.51050 → **35**, margin 0.0105), `D' = 3` (120.4535 → 120), `D' = 1` (198.594 → 199),
`D' = 15` (5.99703 → 6, the closest to an integer: 0.003 below 6). The table is non-increasing
and has equal neighbours at `D' = 19, 20` (2, 2) and `21..24` (1).

The nonzero region per shift: `W != 0` iff `D < t_25(s) = ceil(24.5 · 2^s)`, i.e.
`D <= 24` (s = 0), `<= 48` (s = 1), `<= 97` (s = 2), ..., `<= 802815` (s = 15). The table's
lower thresholds `t_k(s) = ceil((k − 1/2) · 2^s)` are the smallest `D` with `D' >= k`.

## Requirements (block contract, over the full input domain)

- **E1 table:** `W(D, 0) = table[D]` for `D <= 24`, every one of the 25 nonzero entries and the
  first zero (`D = 25`).
- **E2 rounding (half up):** for every `s >= 1` and `k`: `D = k·2^s + 2^(s−1) − 1` gives
  `D' = k`; `D = k·2^s + 2^(s−1)` (the tie) gives `D' = k + 1`. Ties round **up**, never to even
  and never down. `s = 0` has no rounding (no `+1/2` effect).
- **E3 shift selection:** each of the 16 shifts selects its own scaling; in particular the
  boundaries `s = 0` (no guard bit), `s = 1` (guard bit = D[0]), `s = 7/8` (the `shift[3]` stage
  boundary of the RTL), `s = 15` (largest: `D' = (D >> 15) + D[14]`, so D[13:0] never matter
  and the guard bit is D[14]). In general `D' = (D >> s) + D[s−1]` for `s >= 1`.
- **E4 saturation to 0:** `W = 0` whenever `D' >= 25`. This covers four structurally different
  cases in the RTL, all of which must give 0:
  (a) `25 <= D' <= 31` (table default),
  (b) rounding carry to `D' = 32` (e.g. s = 1, D = 63; s = 15, D = 2^20 − 1),
  (c) high bits discarded by a shift stage (e.g. s = 0, D = 32..2^20 − 1),
  (d) `D >= 2^20` (bits 20 or 21 set) at every shift, including **`D >= 2^21`** (bit 21; outside
  the controller's consistent-tape range, see U2) and `D = 2^22 − 1`.
  No wrap-around: a large D must never alias to a small one (e.g. `D = 2^20` must not give 255).
- **E5 all output bits:** W is 8 bits, unsigned; 255 = all ones must appear (D' = 0).
- **E6 REGISTERED = 0 (chip):** purely combinational: `W = W(D, shift)` in the same cycle,
  `done = start` in the same cycle, no dependence on `clk` or `rst_n`, no state, no latch.
  Latency 0.
- **E7 REGISTERED = 1 (block test):** at a rising edge with `rst_n = 0`: `done ← 0`, `W ← 0`
  (reset has priority over `start`). With `rst_n = 1`: `done ← start`; if `start`, `W ←
  W(D, shift)` sampled at that edge, else W holds. So: `done` is high in the cycle after each
  accepted start, for exactly one cycle per pulse (high continuously under back-to-back starts);
  W is valid when `done` is high and **holds** (whatever D/shift do) until the next start or
  reset. Latency 1 cycle, not 0 (no combinational path from D/shift/start to W/done) and not 2.
  Outputs are Q of 9 positive-edge flops on `clk`; no latch, no negedge, no async reset.
- **E8 power-up (REGISTERED = 1):** the 9 flops have no defined power-up value; nothing is
  required before the first reset cycle. After a reset cycle the behaviour is fully determined
  (both copies of a two-copy miter agree from the cycle after the first `rst_n = 0` edge).
  An `initial` value is a synthesis/sim mismatch (GF180 flops have no init) and is not allowed.
- **E9 independence:** for REGISTERED = 0, `W` depends only on `(D, shift)` and `done` only on
  `start`. For REGISTERED = 1, the next W depends on `(rst_n, start, D, shift, W)` only.

## Usage invariants (attention_controller; for in-context reasoning only)

The block contract above must hold without these. They decide whether a surviving mutant is a real
gap (block-level bug) or only in-context equivalent.

- U1 `exp_lut #(.REGISTERED(0))`, `start = 1'b0`, so `done = 0` (`exp_done` is unused).
  `clk`/`rst_n` connected but unused. Any combinational implementation with E1–E5 is acceptable
  in context.
- U2 `D = score` (mac_unit `S`). W is used only in state VALUE (mac `accum_en`; `x = {1'b0, W}`,
  `L_next = L + W`); in every other state its value has no effect (term gated by `accum_en`,
  L updated only when `accum_en`). In VALUE, `S` holds `D = M − S_t` for the current token.
  With a consistent tape (pass-2 rows equal to pass-1 rows), `0 <= D <= SCORE_MAX − SCORE_MIN =
  1,048,576 − (−1,040,384) = 2,088,960 = 0x1FE000 < 2^21`: bit 20 is reachable, **bit 21 is
  not**. With an inconsistent tape or `cont = 1` before any fresh run (documented as garbage),
  D is an arbitrary 22-bit value (negative M − S wraps to D >= 2^21, which must give 0 per E4d).
- U3 `shift = score_shift`, any of 0..15 (host config frame), held from start to idle.
- U4 Hence in context: every shift, D in `[0, 0x1FE000]`, all table entries and all four
  saturation mechanisms are reachable; only `D >= 2^21` is restricted to the garbage/misuse case.
- U5 The block's W feeds the shared 22-bit adder and `l_adder` in mac_unit; D comes straight from
  the S flops. Optimizations across that boundary are a cluster-level matter (D7), not allowed
  inside the block contract.

## Mutants that should survive (equivalences)

- Any re-encoding of the barrel shifter / guard / index logic with the same function (e.g. a
  shift-then-round formulation `(D + 2^(s−1)) >> s` at 23 bits with a `< 25` compare, a direct
  25-entry compare chain, a 32-entry case with explicit zeros, merging the `out_of_range` terms
  into a single compare `D >= t_25(s)`).
- `|diff[21:20]` written as `diff >= 2^20`.
- For REGISTERED = 1: `if (start) W_r <= weight` written as `W_r <= start ? weight : W_r`.
- Not equivalent at block level but equivalent in context (must be **killed** by the block
  contract): ignoring D[21]; W depending on `rst_n` for REGISTERED = 0; `done` tied 0 for
  REGISTERED = 0 (chip ties start = 0).

## What an independent reference must compute

- The table from the mathematical definition (`255 · e^(−n/4)`, rounded), not copied from the RTL
  or from `EXP_TABLE`, with the rounding decision certified (near-ties at n = 8 and n = 25).
- `D'` by a formulation that is not the RTL's (no barrel shifter with a guard bit, no
  `out_of_range` decomposition): e.g. exact rationals `floor(D/2^s + 1/2)` or the threshold
  count `#{k : D >= ceil((k − 1/2)·2^s)}`.
- Over the **whole** 22-bit D × 16 shift domain (2^26 points; exhaustive is cheap), not only the
  in-context score range; plus the sequential behaviour of REGISTERED = 1 (reset priority, hold,
  done pulse, latency) and `done = start` for REGISTERED = 0.

## Agent 2's own reference and result on the golden

`review/ref/run_ref.sh` (`ref_exact.py` → `table.json`, `ref_threshold.v`, `ref_exp_lut.v`). Updated after
user decision D9 (formal only, no exhaustive testing). The exhaustive Verilator sweeps I ran before D9 (both REGISTERED
values, 0 mismatches) are kept in `superseded_pre_D9/` and are not evidence.

| Check | Result |
|---|---|
| Table certified by rational intervals (n = 0..40), first zero at n = 25, stays 0 | pass (exact arithmetic) |
| EQY, golden vs `ref_exp_lut.v`, REGISTERED = 0 (combinational: complete) | proven (PASS, 3 partitions) |
| EQY, golden vs `ref_exp_lut.v`, REGISTERED = 1 (state matched by name, depth-1 induction: unbounded) | proven (PASS, 12 partitions) |
| Yosys SAT miter, golden (REGISTERED = 0) vs threshold-chain reference, W and done, all inputs | proven |
| Negative controls: m19 (one rare point) FAILs every formal check at r0 and r1; m23 (no hold) FAILs at r1 only | as required |
| `EXP_TABLE` of the Python model equals the certified table; `exp_weight()` agrees at 49,945 points | pass-sampled (checks the spec model, not the design) |
