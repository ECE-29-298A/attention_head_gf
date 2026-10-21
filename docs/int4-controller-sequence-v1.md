# INT4 attention controller sequence — version 1

This is the design-level sequence agreed for the first controller. It preserves
the existing `score_mac`, `max_reg`, and `accum` blocks, uses one pass over K,
saves scores, and generates 8-bit LUT weights.

The memory interface below uses logical byte requests. Device-specific xSPI
commands belong in a separate memory-interface block.

For the implemented prototype and its interfaces, see [controller.md](controller.md).
The state names below describe the design sequence; the implementation combines
some transitions and reuses memory request/wait states.

## 1. Fixed baseline

- One query per transaction.
- Four signed INT4 components per Q, K, and V vector.
- Configurable token count: 1–16.
- Signed 10-bit scores and maximum.
- Unsigned 8-bit LUT weights.
- Unsigned 12-bit denominator.
- Four signed 16-bit weighted sums.
- Four signed 8-bit output codes, representing value × 16.

Q, K, and V are computed externally. Before starting, the host must finish
loading K and V into external memory.

The controller performs one operation at a time. Memory transfers and arithmetic
do not overlap in this first version.

## 2. Storage and packing

Use byte-addressed external memory with separate regions:

| Region | Layout | Maximum size |
|---|---|---:|
| K | Two bytes per token | 32 bytes |
| V | Two bytes per token | 32 bytes |
| Scores | Two bytes per token | 32 bytes |
| Weights | One byte per token | 16 bytes |

For K and V:

- First byte: component 0 in bits `[3:0]`, component 1 in `[7:4]`.
- Second byte: component 2 in bits `[3:0]`, component 3 in `[7:4]`.
- Interpret each nibble as signed two's-complement.

Store each score sign-extended from 10 bits to 16 bits, low byte first. On
readback, recover the signed score from bits `[9:0]`.

Keep these locally:

- Four Q components, occupying 16 bits in total.
- A two-byte operand buffer, reused for K and V.
- A 10-bit saved-score register.
- An 8-bit current-weight register.
- Token index `j`, component index `c`, and output index `o`.
- The existing maximum, score accumulator, denominator, and weighted-sum registers.
- A result register holding one output byte until accepted.

For version 1, use fixed, non-overlapping memory base addresses. Only Q and N
need to change between transactions.

## 3. Interfaces the controller expects

### Memory interface

A request contains:

`request_valid, write, address, write_data`

The memory block supplies:

`request_ready, response_valid, read_data`

Contract:

- A request is accepted on a rising edge when `request_valid && request_ready`.
- The controller holds request fields stable until accepted.
- Every request returns one completion response, including writes.
- Only one request may be outstanding.
- Read data is valid with the completion response.
- A write response means that write is complete.
- Responses arrive no earlier than the cycle after request acceptance.

Each logical byte read or write below therefore has a **REQUEST** substate and
a **WAIT_RESPONSE** substate. Increment counters only after the response.

### Existing arithmetic blocks

Use their existing `clear` and `en` inputs:

- `score_mac`: `qi`, `ki` → `S`
- `max_reg`: `S_in` → `M`
- `accum`: `W`, `v0..v3` → `L`, `O0..O3`

Default all `clear` and `en` signals low. Assert them only in the states listed
below. Reset takes priority over clear; clear takes priority over enable.

### New arithmetic blocks

Use a simple start/completion interface:

- Exponent: `start, maximum, score` → `done, weight`
- Divider: `start, numerator_sum, denominator` → `done, result`

Pulse `start` for one cycle. Keep input registers stable while waiting. These
blocks must return `done` in a later cycle, with the result valid at that time.

## 4. State sequence

State actions occur on the rising clock edge at the end of the state.

### Phase A — initialize

| State | Action | Next |
|---|---|---|
| `IDLE` | Wait for a start request with valid Q and N | `INIT` |
| `INIT` | Initialize the transaction: retain accepted Q/N; set `j=0`; clear score MAC, maximum register, and accumulator; clear transaction `done` | `KEY_READ_0` |

Q and N must be captured on the edge accepting start. The implemented controller
also clears `done` and initializes `j` on that edge, then clears arithmetic
blocks in `INIT`.

Store N in five bits so that 16 is representable. The four-bit token index `j`
ranges from 0 to N−1.

### Phase B — read K once, save scores, find maximum

| State | Action | Next |
|---|---|---|
| `KEY_READ_0` | Read `K_BASE + 2j` into operand byte 0 | `KEY_READ_1` |
| `KEY_READ_1` | Read `K_BASE + 2j + 1` into operand byte 1 | `SCORE_CLEAR` |
| `SCORE_CLEAR` | Assert `score_mac.clear`; set `c=0` | `SCORE_MAC` |
| `SCORE_MAC` | Assert `score_mac.en`; supply `Q[c]` and `K[c]` | Repeat for four components, then `SCORE_CAPTURE` |
| `SCORE_CAPTURE` | Capture completed `S` into saved-score register; assert `max_reg.en` with `S_in=S` | `SCORE_WRITE_0` |
| `SCORE_WRITE_0` | Write low byte of sign-extended score to `SCORE_BASE + 2j` | `SCORE_WRITE_1` |
| `SCORE_WRITE_1` | Write high byte to `SCORE_BASE + 2j + 1` | `KEY_NEXT` |
| `KEY_NEXT` | If `j < N−1`, increment `j`; otherwise set `j=0` | `KEY_READ_0` or `SCORE_READ_0` |

**Timing requirement:** `SCORE_CAPTURE` must follow the fourth MAC cycle.
Capturing the score or updating the maximum on the fourth MAC edge would use
the previous partial sum.

After the last token, M contains the final maximum and memory contains all
scores. K is no longer needed for this query.

### Phase C — generate and save weights

| State | Action | Next |
|---|---|---|
| `SCORE_READ_0` | Read low score byte from `SCORE_BASE + 2j` | `SCORE_READ_1` |
| `SCORE_READ_1` | Read high score byte; reconstruct signed 10-bit score | `EXP_START` |
| `EXP_START` | Pulse exponent `start`, supplying final M and saved score | `EXP_WAIT` |
| `EXP_WAIT` | Wait for `done`; capture returned weight | `WEIGHT_WRITE` |
| `WEIGHT_WRITE` | Write weight to `WEIGHT_BASE + j` | `WEIGHT_NEXT` |
| `WEIGHT_NEXT` | If `j < N−1`, increment `j`; otherwise set `j=0` | `SCORE_READ_0` or `ACCUM_CLEAR` |

The exponent block must match the current Python `exp_weight()` exactly:

```text
D = M - S
A = 23 * D
n = A >> 5
r = (A >> 1) & 15
```

Using the existing 16-entry, 8-bit table:

- If `n == 0`: `W = table[r]`.
- If `1 <= n <= 8`: `W = (table[r] + 2^(n−1)) >> n`.
- Otherwise: `W = 0`.

Use a widened intermediate for the rounding addition.

**Do not update the denominator during this phase.**

### Phase D — accumulate weighted values

| State | Action | Next |
|---|---|---|
| `ACCUM_CLEAR` | Assert `accum.clear` to initialize L and all four O registers | `WEIGHT_READ` |
| `WEIGHT_READ` | Read `WEIGHT_BASE + j` into current-weight register | `VALUE_READ_0` |
| `VALUE_READ_0` | Read `V_BASE + 2j` into operand byte 0 | `VALUE_READ_1` |
| `VALUE_READ_1` | Read `V_BASE + 2j + 1` into operand byte 1 | `ACCUM_STEP` |
| `ACCUM_STEP` | Assert `accum.en` for one cycle with W and all four signed V components | `VALUE_NEXT` |
| `VALUE_NEXT` | If `j < N−1`, increment `j`; otherwise set `o=0` | `WEIGHT_READ` or `DIV_START` |

Each `ACCUM_STEP` performs:

```text
L   <- L + W
O_i <- O_i + W * V_i    for i = 0, 1, 2, 3
```

The existing accumulator computes all four products in parallel.

Assert `accum.en` exactly once per token. Leave it low during every memory-wait
cycle.

### Phase E — normalize and output

| State | Action | Next |
|---|---|---|
| `DIV_START` | Pulse divider `start` with `O[o]` and L | `DIV_WAIT` |
| `DIV_WAIT` | Wait for divider `done`; capture signed output code | `OUTPUT_WAIT` |
| `OUTPUT_WAIT` | Assert output-valid and hold result stable until output-ready | `OUTPUT_NEXT` |
| `OUTPUT_NEXT` | If `o < 3`, increment `o`; otherwise finish | `DIV_START` or `COMPLETE` |
| `COMPLETE` | Clear busy; set sticky transaction-done | `IDLE` |

The divider must match the current Python `divide_round()`:

```text
Y = round(16 * O / L)
```

Use nearest rounding with ties away from zero. Divide the unsigned magnitude,
then restore the sign.

For valid transactions, at least one weight is 255, so L is nonzero.

In this version, transaction-done means **all four output bytes have been
accepted**. It remains high until the next accepted start or reset. The prototype
performs `OUTPUT_NEXT` decisions inside `OUTPUT_WAIT` on output acceptance.

## 5. Reset and stall behavior

- Reset aborts the transaction and clears controller status and arithmetic blocks.
- Reset must also cancel outstanding memory-interface activity, or drain it
  before a new transaction begins. A stale response must not be consumed by a
  new transaction.
- Accept a new start only in `IDLE`, with N in 1–16 and reset released.
- Keep memory request fields stable until accepted.
- Do not advance counters during stalls.
- Hold output data and output-valid stable until accepted.
- The host must not modify active K/V regions while busy.
- No overlap, prefetching, or general-purpose DMA descriptors are required for
  version 1.

## 6. First integration checks

1. **N=1:** decoded output equals the supplied V exactly.
2. **Equal scores:** outputs equal the rounded component-wise mean of V.
3. **Negative scores:** maximum tracking still works.
4. **N=16 and extreme INT4 values:** sums remain within allocated widths.
5. **Memory and output stalls:** results remain unchanged and no token is counted twice.
6. **Back-to-back transactions:** no stale maximum, sums, or memory responses.
7. **End-to-end comparison:** every output code matches the existing integer Python model.

The prototype tests use a simple memory model and behavioral exponent/divider
stand-ins. Passing those tests validates controller sequencing, not an actual
xSPI device interface or synthesizable exponent/divider implementation.
