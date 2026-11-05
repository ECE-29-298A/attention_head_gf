# Arithmetic blocks

`score_mac`, `max_reg` and `accum` are the datapath blocks the controller
(`docs/controller.md`) drives. All three share the same control pattern:

- Synchronous active-low `rst_n`, then `clear`, then `en`. Clear wins over
  enable when both are high. With neither, outputs hold.
- Outputs are registered and update on the rising edge after the inputs.

Q, K and V components are signed INT4 (-8..7). Weights are unsigned 8-bit.

## `score_mac` (`src/score_mac.v`)

Dot product of one Q and one K, one component per cycle.

| Port | Width | Meaning |
|---|---:|---|
| `clear` | 1 | Zero `S` before a new key |
| `en` | 1 | Add `qi * ki` to `S` |
| `qi`, `ki` | signed 4 | One component of Q and K |
| `S` | signed 10 | Running sum |

Usage: pulse `clear`, then four `en` cycles (components 0..3). `S` holds the
score on the cycle after the fourth enable. Range is -224..256, which fits in
10 bits signed. Matches Python `dot4`.

## `max_reg` (`src/max_reg.v`)

Running maximum of scores in one query.

| Port | Width | Meaning |
|---|---:|---|
| `clear` | 1 | New query: reset `M` |
| `en` | 1 | `S_in` holds a finished score |
| `S_in` | signed 10 | Score from `score_mac` |
| `M` | signed 10 | Largest score seen so far |

Reset and clear set `M` to -224, the smallest possible INT4 score, so the first
enabled score always replaces it. Equal scores leave `M` unchanged. Change this
reset value if the inputs widen (e.g. INT8).

## `accum` (`src/accum.v`)

Sums for the weighted average, one token per enable.

| Port | Width | Meaning |
|---|---:|---|
| `clear` | 1 | Start of accumulation pass: zero all sums |
| `en` | 1 | `W` and `v0..v3` are valid for one token |
| `W` | unsigned 8 | Token weight (0..255) |
| `v0..v3` | signed 4 | Token V vector |
| `L` | unsigned 12 | Sum of `W` (divider denominator) |
| `O0..O3` | signed 16 | Sum of `W * vi` (divider numerators) |

`W` is zero-extended before the signed multiply. For N <= 16 tokens, `L` is at
most 4080 and `Oi` stays within -32640..28560, so neither width overflows.
The divider then encodes `Oi / L` as `round(16 * Oi / L)`. Uses four multipliers in parallel; sharing
the `score_mac` multiplier would need extra control logic.

## `exp_lut` (`src/exp_lut.v`)

Softmax weight for one token: W = round(255 · e^(−(M−S)/2)).

| Port | Width | Meaning |
|---|---:|---|
| `start` | 1 | One-cycle pulse; `M` and `S` sampled on this edge |
| `M` | signed 10 | Final maximum score |
| `S` | signed 10 | This token's score |
| `done` | 1 | High for one cycle, the cycle after `start` |
| `W` | unsigned 8 | Weight; valid with `done`, held until the next `start` |

Scores are integers, so D = M − S is too, and W rounds to 0 once D >= 13.
So the whole exponent is a 13-entry table indexed by D:

| D | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13+ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| W | 255 | 155 | 94 | 57 | 35 | 21 | 13 | 8 | 5 | 3 | 2 | 1 | 1 | 0 |

This replaced the proposal's 23/32 trick (W = 255 · 2^(−23D/32), table plus
shifter). That method also only produces 13 values, but is slightly off at
D = 1, 3, 5 and takes about 2.5x the gates. If `M < S` (should never
happen), D is treated as 0, so W = 255. Matches Python `exp_weight` /
`EXP_TABLE`.

## `divider` (`src/divider.v`)

Iterative signed normalization: `result = round(16 * sum_in / denominator)`,
nearest with ties away from zero. Uses a 19-bit shift/subtract division datapath
and one rounding/sign cycle. See [divider.md](divider.md) for register widths,
invalid-input behavior, port descriptions, and exact start/done timing.

The [attention controller](controller.md) instantiates all five arithmetic blocks
directly. The exponent and divider remain separate modules, connected by internal
wires; no additional core wrapper is required.

## Verification

Cocotb + Icarus, one module per run, from `test/blocks`:

```sh
make score_mac
make max_reg
make accum
make exp_lut   # every valid (M, S) pair, 115,921 cases
```

The divider and integrated controller use Python + NumPy/Verilator runners. From
the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 test/divider/run.py
PYTHONDONTWRITEBYTECODE=1 python3 test/controller/run.py
```

CI is configured to run all four existing block tests, the standalone divider
test, one integrated controller regression, and the current Tiny Tapeout template
test. Block tests retain exhaustive/boundary coverage beyond the integrated
queries; the duplicate mock-arithmetic regression has been removed. The standalone
Verilator runners use temporary build directories. Local verification results
and limits are in the linked docs.
