# Integrated two-pass INT4 attention controller (version 2)

`src/attention_controller.sv` instantiates `score_mac`, `max_reg`, `accum`,
`exp_lut` and `divider`. These remain separate, reusable RTL modules; their
arithmetic is unchanged. It is a complete arithmetic core, not a Tiny Tapeout pin
wrapper. The existing `project.v`, `info.yaml`, default test and physical build
still select the template project. This prototype is not tapeout-ready.

Instantiate `attention_controller` directly for system integration. The former
`attention_core` wiring-only wrapper has been removed. All `exp_*` and `div_*`
handshakes are now internal wires, not controller ports. This hierarchy change
does not change the state sequence, arithmetic results or cycle counts.

| Instance inside the controller | Module | Role |
|---|---|---|
| `score_unit` | `score_mac` | Four-cycle Q.K dot product |
| `max_unit` | `max_reg` | Retain the first-pass maximum |
| `accum_unit` | `accum` | Sum weights and weighted V components |
| `exponent_unit` | `exp_lut` | Generate the current token's weight |
| `divider_unit` | `divider` | Normalize each output component |

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

## External interface

| Group | Signals | Contract |
|---|---|---|
| Clock/reset | clk, rst_n | One shared clock, synchronous active-low reset |
| Request | start, start_ready, token_count, query_packed | Capture N=1..16 and packed Q on acceptance |
| Status | busy, done | Busy through output acceptance; done sticky until accepted start/reset |
| Memory request | mem_req_valid, mem_req_ready, mem_addr, mem_write, mem_wdata | Byte reads only; write and write-data permanently zero |
| Memory response | mem_rsp_valid, mem_rdata | Exactly one response per accepted read, in a later cycle |
| Output | out_valid, out_ready, out_data | Four signed codes in component order; hold stable until accepted |

- Memory: request accepted on `mem_req_valid && mem_req_ready`. Exactly one
  response per read; completion must arrive in a later
  cycle, never the acceptance cycle. `mem_rdata` is valid with `mem_rsp_valid`.
  No response-ready signal is needed: only one request is outstanding. Hold
  request fields stable until accepted. `mem_write=0` and `mem_wdata=0` are
  constant compatibility outputs for the existing adapter interface.
- Output: transfers on `out_valid && out_ready`; byte is signed, value=code/16.
- Start: `start_ready` is high only in idle with N in 1..16 and reset released.
  Invalid N is not accepted; starts while busy are ignored. A held start can
  launch another query when the controller returns idle, so deassert after
  acceptance. `done` clears on accepted start/reset and rises after readout.
- Reset: synchronous active low, shared automatically by all internal arithmetic
  blocks. The external memory adapter must cancel or drain pending responses.
  Do not reconnect a stale completion to a new run.

## Internal arithmetic handshakes

- Exponent: pulse `exp_start` with stable signed `exp_max`/`exp_score`.
  `exponent_unit` registers `exp_done` and the unsigned 8-bit `exp_weight` on
  the accepted start edge; the controller consumes them on the following edge.
  It matches Python `exp_weight`: a 13-entry table of round(255·e^(−D/2))
  indexed by D=M−S, returning 0 for D>=13. See [blocks.md](blocks.md).
- Divider: pulse `div_start` with signed 16-bit `div_sum` and unsigned 12-bit
  `div_denominator`, stable until completion. `divider_unit` takes 19 division
  steps and one rounding/sign step; the controller consumes `div_done` and
  signed 8-bit `div_result` 21 clocks after accepted start. It matches Python
  `divide_round`: round(16*sum/denominator), ties away from zero. See
  [divider timing and contract](divider.md).

These signals connect modules inside the controller; no host or testbench must
provide arithmetic results or completions.

## Remaining system work

There is no SPI/xSPI implementation, general DMA, bus arbitration, timeout,
memory-error recovery, clock-domain crossing or Tiny Tapeout `ena` handling in
this prototype. The host-facing wrapper and external-memory adapter remain to
be built, including host-readable output buffering. All arithmetic engines are
implemented and connected inside `attention_controller`.
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
repository free of generated files. The testbench supplies only a byte-memory
model and host signals. Every score, weight, weighted sum and normalized result
comes from the real RTL. Physical xSPI timing is not modeled.

Coverage: 138 directed/random queries across all token counts, including a
maximum occurring at the last token, all-negative scores, positive/negative
rounding ties, neighboring rounding boundaries, and zero numerators at the
largest denominator. Check both score
passes, exponent inputs/weights, every running sum, final numerators/denominator,
and output codes. Require 8N score MAC enables, N maximum updates, N accumulator
updates, N exponent starts and four divider starts. Each K byte is read twice,
each V byte once, with zero writes or accesses outside active K/V rows.

Run three randomized memory/output-stall schedules, three fixed memory latencies
(2, 8 and 32 clocks from accepted read to sampled response), and one randomized
run with relocated K/V bases (0x1200 and 0x3400): 966 query executions total.
Also check stable stalled requests/outputs, stable arithmetic operands, invalid N,
changed configuration/start while busy, reset during each K pass, LUT start and
result, V fetch, all 20 busy divider stages and output wait, sticky done, and
consecutive queries without reset. Check the real divider's completion latency.
All simulations have bounded timeouts. Reset tests cancel pending testbench
memory responses; real bus cancellation/draining still needs implementation.

The duplicate `test/core` suite has been merged into `test/controller`. The old
mock-exponent/mock-divider testbench and legacy `--compare-ref` benchmark mode
have been removed; their tracked versions remain in Git history. Standalone
block tests remain because they cover exhaustive arithmetic pairs, rounding
boundaries and invalid requests not all exercised by whole attention queries.
See [blocks.md](blocks.md) and [divider.md](divider.md).

Local verification on November 5, 2026 with Verilator 5.052 passed all seven
controller configurations (966 query executions) and the 108,641-vector divider
suite. All seven cycle totals match the pre-refactor real-core regression.
Lint reports only the existing accumulator width-extension and missing-final-
newline warnings. The unchanged Cocotb block/template tests were not rerun
locally (Cocotb/Icarus unavailable); CI still includes them. The updated CI has
not been run remotely as part of this task.

## Build

Compile the controller and its five arithmetic modules:

```text
src/attention_controller.sv
src/score_mac.v
src/max_reg.v
src/accum.v
src/exp_lut.v
src/divider.v
```

No chip pins or Tiny Tapeout physical-build entry point are changed. Area/timing
closure and physical checks remain; no synthesis or silicon claim is made.

## Comparison with version 1

The old controller uses 10 memory-byte transfers and four score MAC cycles per
token. Version 2 uses six read transfers and eight score MAC cycles per token.
LUT calls, accumulator updates and divisions are unchanged. At N=16, traffic
falls from 160 to 96 bytes, with 64 extra score MAC cycles.

The following measurements are historical; the obsolete comparison runner is
no longer part of the active tests. They compared both versions using the same
135 vectors, always-ready outputs, fixed memory delays, and exponent/divider
stand-ins completing 3/21 clocks after start. Counts include accepted start
through transaction completion, excluding idle gaps and reset tests. They are
not actual xSPI timing or silicon results.

These historical timings use arithmetic stand-ins. They are not the latency of
the now-connected real core, whose LUT completion is consumed one clock after
start and whose divider completion is consumed 21 clocks after start.

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
See `python/accuracy_report.md` for the known limitations.
