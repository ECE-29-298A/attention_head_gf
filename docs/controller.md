# Two-pass INT4 controller prototype (version 2)

`src/attention_controller.sv` connects the existing `score_mac`, `max_reg` and
`accum` unchanged. It is an internal sequencing core, not a Tiny Tapeout pin
wrapper. The existing `project.v`, `info.yaml`, default test and physical build
still select the template project. This prototype is not tapeout-ready.

See [the version-2 sequence](int4-controller-sequence-v2.md) for the complete
state table. [Version 1](int4-controller-sequence-v1.md) is historical: its
external score and weight storage has been removed.

## Sequence

1. Accept `start && start_ready`; latch packed Q and N (1..16).
2. **Pass 1:** read each K, execute four score MAC cycles and update the maximum
   on the following cycle. Discard the individual score after updating maximum.
3. Reset the token index, freeze the maximum, and clear the weighted accumulators.
4. **Pass 2:** read K again and recompute its score; generate its 8-bit LUT weight,
   hold that weight locally while reading V, and pulse the accumulator once.
   Repeat for every token. This is the only phase that adds weights to L.
5. Request division for each of four sums and hold each output until accepted.
6. Assert sticky `done` and return idle after all four outputs are accepted.

The detailed state names are in the controller enum. `MEM_REQUEST` and
`MEM_WAIT` are reused with a registered return state. Phase changes and counters
advance only after completed transfers. `second_pass` selects whether score
capture updates maximum or starts an exponential calculation. All arithmetic enables are inactive
during memory stalls. Four V multipliers remain in `accum`; no sharing redesign
is attempted. Config inputs may change after start; they have been latched.

## Byte memory map (parameterized base addresses)

| Region | Default base | Bytes per token | Maximum bytes |
|---|---:|---:|---:|
| K | 0x00 | 2 | 32 |
| V | 0x20 | 2 | 32 |

Q is a 16-bit local register: component 0 is bits 3:0, through component 3 in
bits 15:12. K/V use the same nibble order, low byte first. Only the current
signed 10-bit score and unsigned 8-bit weight are retained locally. There is no
external score/weight array and no memory writes from this controller.
Alternate bases must remain non-overlapping for N=16 and fit the 16-bit address
space. The host loads K/V before start and must not change them while busy.
K must remain identical across the two passes. The core keeps Q internally.

## External engine contracts

- Memory: request accepted on `mem_req_valid && mem_req_ready`. Exactly one
  response per read; completion must arrive in a later
  cycle, never the acceptance cycle. `mem_rdata` is valid with `mem_rsp_valid`.
  No response-ready signal is needed: only one request is outstanding. Hold
  request fields stable until accepted. `mem_write=0` and `mem_wdata=0` are
  constant compatibility outputs for the existing adapter interface.
- Exponent: pulse `exp_start`; use stable signed `exp_max`/`exp_score`; return
  `exp_done` and unsigned 8-bit weight in a later cycle. Match Python
  `exp_weight`, including its n<=8 rounding branch.
- Divider: pulse `div_start`; use signed 16-bit `div_sum` and unsigned 12-bit
  `div_denominator`; return `div_done` with signed 8-bit result in a later cycle.
  Match Python `divide_round`: round(16*sum/denominator), ties away from zero.
- Output: transfers on `out_valid && out_ready`; byte is signed, value=code/16.
- Start: `start_ready` is high only in idle with N in 1..16 and reset released.
  Invalid N is not accepted; starts while busy are ignored. A held start can
  launch another query when the controller returns idle, so deassert after
  acceptance. `done` clears on accepted start/reset and rises after readout.
- Reset: synchronous active low. Reset all attached engines together and cancel
  pending memory responses. Do not reconnect a stale completion to a new run.

There is no SPI/xSPI implementation, general DMA, bus arbitration, timeout,
memory-error recovery, clock-domain crossing or Tiny Tapeout `ena` handling in
this prototype. The host-facing wrapper and actual engines remain to be built.
The two-pass arithmetic now follows the original proposal. Data delivery still
differs: the controller rereads host-populated external memory instead of asking
the host to resend streams. The existing one score multiplier plus four value
multiplications are retained; this is not the proposal's single shared MAC.

## Verification

Run from the repository root with Python + NumPy and Verilator installed:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 test/controller/run.py
```

Use an absolute path to the script when outside the repository. The runner
generates expected outputs, intermediate scores and weights using the existing
Python model. It builds and simulates in a temporary directory, leaving the
repository free of generated files. The testbench supplies a byte-memory model
and delayed behavioral exponent/divider stand-ins; it does not verify a real
exponent/divider circuit or physical xSPI timing.

Coverage: 135 directed/random queries across all token counts, including a
maximum occurring at the last token and all-negative scores. Check both score
passes, exponent inputs/weights, every running sum, final numerators/denominator,
and output codes. Require 8N score MAC enables, N maximum updates, N accumulator
updates, N exponent starts and four divider starts. Each K byte is read twice,
each V byte once, with zero writes or accesses outside active K/V rows.

Run three randomized stall/latency schedules and three fixed-latency schedules.
Also check stable stalled requests/outputs, stable arithmetic operands, invalid N,
changed configuration/start while busy, reset during each K pass, exponent wait,
V fetch, divider wait and output wait, sticky done, and consecutive queries
without reset. All simulations have bounded timeouts. Reset tests cancel pending
mock-engine activity; real bus cancellation/draining still needs implementation.

## Comparison with version 1

The old controller uses 10 memory-byte transfers and four score MAC cycles per
token. Version 2 uses six read transfers and eight score MAC cycles per token.
LUT calls, accumulator updates and divisions are unchanged. At N=16, traffic
falls from 160 to 96 bytes, with 64 extra score MAC cycles.

To reproduce a comparison against the saved-score controller at the pre-rewrite
commit (no checkout or worktree changes):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 test/controller/run.py --compare-ref 9607f0cc0065df7ab9bbfd96b8d348127edd6665
```

The runner extracts that controller into a temporary directory and tests both
versions with the same current arithmetic blocks, vectors and testbench. Legacy
mode checks the old storage/access schedule; new mode checks the two-pass one.
For timing, ready is always asserted when eligible, output is always accepted,
and memory responses are sampled exactly 2, 8 or 32 cycles after acceptance.
Exponent/divider mock completions are sampled 3/21 cycles after their starts.
Cycle counts include the accepted start edge through the edge completing the
transaction; they exclude idle gaps and reset tests. These are controller-model
measurements, not actual xSPI timing or silicon results.

Measured on November 3, 2026 with Verilator 5.052 and all 135 vectors:

| Memory response cycles | Version 1 total cycles | Version 2 total cycles | Reduction | N=16 query cycles, old → new |
|---:|---:|---:|---:|---:|
| 2 | 78,966 | 66,228 | 16.13% | 1,008 → 832 |
| 8 | 148,446 | 107,916 | 27.30% | 1,968 → 1,408 |
| 32 | 426,366 | 274,668 | 35.58% | 5,808 → 3,712 |

Each N=16 query has identical latency within a fixed scenario because the
mock arithmetic delays are fixed. Actual LUT/divider timing, SPI command and
dummy-cycle overhead, burst accesses and overlap can change these figures.
The benchmark tests the sequential byte-request architecture only.

Arithmetic precision remains the existing 8-bit-weight model; exact integer
agreement does not establish the proposal's floating-point error target.
