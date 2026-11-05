# Signed attention divider

`src/divider.v` implements the existing Python `divide_round(O, L)` calculation:

```text
magnitude = 16 * abs(O)
quotient, remainder = divide(magnitude, L)
if 2 * remainder >= L: quotient += 1
result = -quotient if O < 0 else quotient
```

Result is a signed 8-bit code; its real value is code / 16. Rounding is nearest,
with ties away from zero. For example O=1, L=32 gives code 1, and O=-1 gives
code -1. No floating-point operations, `/` or `%` operators are used in the RTL.

## Ports and contract

| Port | Width | Meaning |
|---|---|---|
| `clk` | 1 | Rising-edge clock |
| `rst_n` | 1 | Synchronous active-low reset; aborts in-flight calculation |
| `start` | 1 | Accepted on a rising edge when busy is low |
| `sum_in` | signed 16 | Weighted sum O; latched on accepted start |
| `denominator` | unsigned 12 | Weight sum L; latched on accepted start |
| `busy` | 1 | High from accepted start through the final calculation cycle |
| `done` | 1 | One-cycle pulse with completed result |
| `result` | signed 8 | Held until the next calculation completes, or reset |

Start while busy is ignored, including on the rounding edge. A start may be
accepted on the first edge after completion, while the previous done pulse is
still high before that edge. Pulse start or deassert after acceptance; holding
it high can start a new operation when idle. Inputs may change after acceptance.

On valid INT4 attention inputs, `255 <= L <= 4080` and `-8L <= O <= 7L`.
Thus O is in [-32640, 28560], the numerator fits 19 bits, and output codes lie
in [-128, 112]. The standalone divider also supports other inputs accepted by
the Python function: positive L within its 12-bit port, abs(O) <= 32767, and a
rounded code fitting signed 8 bits.

Invalid requests complete with result 0 at the same latency:

- L=0 (division undefined).
- O=-32768 (scaled magnitude needs 20 bits; outside Python's 19-bit check).
- Rounded output would fall outside [-128, 127].

This is deterministic fallback behavior, not saturation or agreement with the
Python function on invalid inputs: Python asserts on those inputs. There is no
error flag in this minimal interface, so result=0 alone does not indicate an
error. The integrated controller test asserts valid numerators/denominators before every
request. Valid K/V data and the retained max-weight token guarantee L>0.

## Datapath and timing

- A 19-bit combined numerator/quotient register starts with `abs(O) << 4`.
- A 12-bit register stores the partial remainder and another stores L.
- Each step shifts in one numerator bit, compares against L, optionally
  subtracts L, and appends one quotient bit. The trial remainder is widened to
  13 bits for comparison. Once subtraction is selected, its low 12 bits hold
  the complete remainder because the result is less than L (at most 4095).
- After 19 steps, compare twice the final remainder to L. A 20-bit rounded
  magnitude prevents carry-out from wrapping; restore the original sign.

| Edge relative to accepted start | Action |
|---:|---|
| 0 | Latch operands/sign, initialize division, busy becomes high |
| 1–19 | One restoring-division step per clock |
| 20 | Round and restore sign; update result, pulse done, busy becomes low |
| 21 | Consumer samples the done/result from edge 20; done drops unless reset |

`attention_controller` instantiates this module internally and retains the
`DIV_START`/`DIV_WAIT` sequence. It
consumes the result at edge 21 and enters `OUTPUT_WAIT`. The result is not
changed by output stalls, because it has also been captured in the controller.
Reset clears done, result, state and arithmetic registers and prevents any later
completion from the aborted operation.

## Verification

From the repository root, with NumPy and Verilator available:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 test/divider/run.py
```

The runner imports the actual Python `divide_round` function and generates
108,641 vectors: all 1..4095 denominators at directed bounds, every numerator
from -32640 through 28560 at L=4080, both signs around every output rounding
threshold, 10,000 seeded random valid requests, and seven invalid requests.
Invalid expected outputs use the documented RTL fallback rather than Python.
This is not an exhaustive sweep of every numerator/denominator combination.

The RTL test also verifies exact 20-cycle latency, done pulse width, result
holding, changing input operands after start, ignored busy-start requests,
consecutive operations, and reset at every division step and the rounding stage.
Builds/vectors are temporary and deleted after the run. This regression passed
locally with Verilator 5.052 on November 4, 2026.
