# INT4 controller prototype

`src/attention_controller.sv` connects the existing `score_mac`, `max_reg` and
`accum` unchanged. It is an internal sequencing core, not a Tiny Tapeout pin
wrapper. The existing `project.v`, `info.yaml`, default test and physical build
still select the template project. This prototype is not tapeout-ready.

## Sequence

1. Accept `start && start_ready`; latch packed Q and N (1..16).
2. Read each K once, execute four score MAC cycles, capture on the following
   cycle, update maximum and save the signed score.
3. Read scores, request exponent calculation using the final maximum and save
   the returned 8-bit weights.
4. Read each weight and V vector, then pulse the existing accumulator once.
   This is the only phase that adds weights to the denominator.
5. Request division for each of four sums and hold each output until accepted.
6. Assert sticky `done` and return idle after all four outputs are accepted.

The detailed state names are in the controller enum. `MEM_REQUEST` and
`MEM_WAIT` are reused with a registered return state. Phase changes and counters
advance only after completed transfers. All arithmetic enables are inactive
during memory stalls. Four V multipliers remain in `accum`; no sharing redesign
is attempted. Config inputs may change after start; they have been latched.

## Byte memory map (parameterized base addresses)

| Region | Default base | Bytes per token | Maximum bytes |
|---|---:|---:|---:|
| K | 0x00 | 2 | 32 |
| V | 0x20 | 2 | 32 |
| Scores | 0x40 | 2 | 32 |
| Weights | 0x60 | 1 | 16 |

Q is a 16-bit local register: component 0 is bits 3:0, through component 3 in
bits 15:12. K/V use the same nibble order, low byte first. Scores are signed
10-bit values sign-extended to 16 bits, low byte first. Weights are unsigned.
Alternate bases must remain non-overlapping for N=16 and fit the 16-bit address
space. The host loads K/V before start and must not change them while busy.

## External engine contracts

- Memory: request accepted on `mem_req_valid && mem_req_ready`. Exactly one
  response per request, including writes; completion must arrive in a later
  cycle, never the acceptance cycle. `mem_rdata` is valid with `mem_rsp_valid`.
  No response-ready signal is needed: only one request is outstanding. Writes
  are complete when acknowledged. Hold request fields stable until accepted.
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
The saved-score memory phase is new relative to the original proposal.

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

Coverage: 133 directed/random queries across all token counts; exact outputs,
stored scores/weights, per-address read/write counts (K read exactly once),
random request/output stalls and response latencies, stable stalled requests
and outputs, stable arithmetic operands, invalid N, changed config/start while
busy, resets during outstanding memory/exponent/divider/output phases, sticky
done and consecutive queries without reset. There is a bounded timeout.

Arithmetic precision remains the existing 8-bit-weight model; exact integer
agreement does not establish the proposal's floating-point error target.
