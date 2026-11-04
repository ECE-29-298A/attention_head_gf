# INT4 attention controller sequence — version 2

This is the current two-pass sequence in `src/attention_controller.sv`. It
supersedes [version 1](int4-controller-sequence-v1.md). The existing `score_mac`,
`max_reg`, and `accum` blocks are unchanged.

## 1. Numeric contract and data flow

- Q/K/V are precomputed externally: four signed INT4 components per vector.
- One query processes 1–16 K/V rows.
- Score and maximum: signed 10 bits.
- LUT weight: unsigned 8 bits (0–255).
- Denominator L: unsigned 12 bits.
- Four weighted sums O: signed 16 bits each.
- Outputs: four signed 8-bit codes, interpreted as code / 16.

```text
Load Q/N
  -> pass 1: read K -> Q.K -> update maximum (repeat N times)
  -> pass 2: read K -> Q.K -> LUT using final maximum
             -> hold weight -> read V -> update L and all four O (repeat N times)
  -> divide/output each of four components -> done
```

For each token j, pass 1 computes S_j = Q.K_j and keeps M = max(S_j).
Pass 2 recomputes S_j and generates W_j approximately equal to
255 * exp((S_j - M)/2). It then updates L += W_j and O_i += W_j * V_j,i.
Finally, Y_i = round(16 * O_i / L), with ties away from zero.

LUT weights are unnormalized; division by L completes normalization. The common
weight scale cancels in the ratio, but quantization/approximation error remains.
Use the existing Python integer model as the exact reference, not an assumed
floating-point error guarantee.

The controller executes one action at a time. It does not overlap memory and
computation. Four value multiplications remain parallel in `accum`; there is
no new shared-MAC design.

## 2. Storage

| Location | Contents | Capacity |
|---|---|---:|
| External memory at K_BASE (default 0x00) | K vectors | 2N bytes, at most 32 |
| External memory at V_BASE (default 0x20) | V vectors | 2N bytes, at most 32 |
| Local `query` | Active Q | 16 bits |
| Local `operands` | Current K or V vector, reused buffer | 16 bits |
| Local `current_score` | Current pass-2 score for exponent engine | 10 bits |
| Local `maximum` | Final maximum retained across pass 2 | 10 bits |
| Local `weight` | Current weight retained until accumulation | 8 bits |
| Existing accumulator | L and O0–O3 | 12 + 4×16 bits |
| Local `out_data` | Current output byte | 8 bits |

Additional control state includes token count N (five bits), token index
(four bits), component/output indices (two bits each), the pass flag, byte
response latch, address register and memory-return state.

Q components occupy bits [3:0], [7:4], [11:8], [15:12], respectively. K/V use
the same signed nibble order, with the low byte at BASE + 2j and the high byte
at BASE + 2j + 1. Bases must not overlap or wrap the 16-bit address space.

There is no score or weight memory region. The core emits no writes. The host
must load K/V before start and leave them unchanged until the query finishes;
particularly, both K passes must see identical data.

## 3. Handshakes

- Start: rising edge with `start && start_ready` captures Q/N and clears done.
  Ready requires idle, reset released, and N in 1–16. Deassert start after
  acceptance; a continuously asserted start could launch another query later.
- Memory: `mem_req_valid && mem_req_ready` accepts one byte read. Address is
  stable until accepted. `mem_rsp_valid` returns its byte in a later cycle.
  One request is outstanding at a time. Compatibility outputs `mem_write`
  and `mem_wdata` stay zero.
- Exponent: one-cycle `exp_start`, then wait for `exp_done` with `exp_weight`.
  Maximum and score stay stable until completion; no new start while waiting.
- Divider: one-cycle `div_start`, then wait for `div_done` with `div_result`.
  Sum and denominator stay stable until completion; no new start while waiting.
- Output: `out_valid && out_ready` transfers the result at a rising edge.
  Hold data and valid while stalled. Send components in order 0, 1, 2, 3.

Exponent and divider completion must arrive in a later cycle than start, not
on the same edge. Reset all engines together, or drain/discard outstanding
responses before another transaction can start.

## 4. State table (matches the RTL names)

Actions take effect at the rising edge ending the state. The register value
written at that edge is available to the next state.

### Initialization

| State | Action | Next |
|---|---|---|
| `IDLE` | On accepted start: latch Q/N, set token=0 and second_pass=0, clear done | `INIT` |
| `INIT` | Clear score MAC, maximum and accumulator | `KEY0` |

### Key read and dot product — shared by both passes

| State | Action | Next |
|---|---|---|
| `KEY0` | Prepare read of K_BASE + 2×token | Memory request/wait; return to `KEY1` |
| `KEY1` | Copy returned low byte into operands; prepare read of high byte | Memory request/wait; return to `KEY_READY` |
| `KEY_READY` | Copy returned high byte into operands | `SCORE_CLEAR` |
| `SCORE_CLEAR` | Clear score MAC; set component=0 | `SCORE_MAC` |
| `SCORE_MAC` | Enable one Q[component] × K[component] accumulation | Repeat through component 3; then `SCORE_CAPTURE` |
| `SCORE_CAPTURE` | Pass 1: enable max register. Pass 2: latch score into current_score; do not enable max register | Pass 1: `KEY_NEXT`; pass 2: `EXP_START` |

**Capture timing:** the fourth MAC update occurs at the edge leaving
`SCORE_MAC`. `SCORE_CAPTURE` consumes that completed result at the following
edge. Do not merge these two edges when connecting synchronous registers.

### First-pass loop and transition

| State | Action | Next |
|---|---|---|
| `KEY_NEXT` | If token < N−1, increment token | `KEY0` |
| `KEY_NEXT` (last token) | Set token=0 and second_pass=1 | `ACCUM_CLEAR` |
| `ACCUM_CLEAR` | Clear L and O once at the pass boundary; retain M and Q | `KEY0` |

The max register is enabled only by `SCORE_CAPTURE && !second_pass`. Once the
flag is set, the maximum remains fixed through exponent generation, weighted
accumulation, division and output. It is cleared only for the next query/reset.

### Second-pass weight and value processing

| State | Action | Next |
|---|---|---|
| `EXP_START` | Pulse exponent start using current_score and final maximum | `EXP_WAIT` |
| `EXP_WAIT` | Wait; on exp_done capture exp_weight locally | `VALUE0` |
| `VALUE0` | Prepare read of V_BASE + 2×token | Memory request/wait; return to `VALUE1` |
| `VALUE1` | Copy low byte into operands; prepare high-byte read | Memory request/wait; return to `VALUE_READY` |
| `VALUE_READY` | Copy high byte into operands | `ACCUM_STEP` |
| `ACCUM_STEP` | Enable accumulator exactly once: add W to L and W×V_i to all O_i | `VALUE_NEXT` |
| `VALUE_NEXT` | If token < N−1, increment token | `KEY0` to recompute next score |
| `VALUE_NEXT` (last token) | Set output_index=0 | `DIV_START` |

Do not add weights to L in `EXP_WAIT`; the existing accumulator does that in
`ACCUM_STEP`. Keep weight unchanged while fetching V. Do not clear sums between
tokens. The operand buffer can be overwritten with V because the score has
already been captured and its exponent calculated.

The external exponent engine must match Python `exp_weight`: D=M−S,
A=23D, n=A>>5, r=(A>>1)&15. Use the existing table scaled to 255; for n=0
return table[r], for 1≤n≤8 return (table[r]+2^(n−1))>>n, otherwise return 0.
Widen the rounding addition. At least one valid token has W=255, so L>0.

### Normalization and output

| State | Action | Next |
|---|---|---|
| `DIV_START` | Pulse divider start with O[output_index] and L | `DIV_WAIT` |
| `DIV_WAIT` | Wait; on div_done latch signed result code | `OUTPUT_WAIT` |
| `OUTPUT_WAIT` | Hold output valid/data. On acceptance, increment output_index if not last | `DIV_START`, or `COMPLETE` after component 3 |
| `COMPLETE` | Set sticky done; transition to idle, clearing busy | `IDLE` |

The divider implements round(16×O/L), nearest with ties away from zero.
Done means all four bytes were accepted by the attached receiver, which may
eventually be a host-readable result buffer. It does not require the host to
have read a downstream buffer. Done remains set until accepted start/reset.

### Common memory states

| State | Action | Next |
|---|---|---|
| `MEM_REQUEST` | Hold request-valid and address until request-ready | `MEM_WAIT` on acceptance |
| `MEM_WAIT` | Wait for response-valid; latch read byte | Registered `return_state` |

The initiating state sets address and return_state before entering
`MEM_REQUEST`. No arithmetic enable is asserted in either memory state.

## 5. Reset, testing and remaining scope

Synchronous active-low reset aborts the transaction. Cancel or discard pending
memory/arithmetic responses and restart from idle with fresh Q/N. Real xSPI
abort behavior is not implemented by this prototype.

Verification must check both score passes against Python, final maximum before
any exponent starts, weights, running sums, outputs, and all stalls/handshakes.
Require exactly two reads per active K byte, one per V byte, zero writes,
8N MAC enables, N max updates, N accumulator updates and four divisions.
Exercise N=1/N=16, negative scores, last-token maximum, memory and output
stalls, reset in both passes, and back-to-back queries. See [controller.md](controller.md)
for the runnable tests, measured comparison and limitations.

The host SPI wrapper, real xSPI adapter/DMA, exponent RTL, divider RTL and
Tiny Tapeout top-level integration remain separate work. The current exponent,
divider and memory in the testbench are behavioral stand-ins.
