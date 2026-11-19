# Arithmetic blocks

> Historical INT4 documentation. The current RTL is INT8; see
> [the integration report](integration-report.md) and module port declarations
> before using the widths and cycle counts below.

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

Softmax weight for one token: W = round(255 · e^(−(M−S)/4)). One score unit is 0.25 nat.

| Port | Width | Meaning |
|---|---:|---|
| `start` | 1 | One-cycle pulse; `M` and `S` sampled on this edge |
| `M` | signed 18 | Final maximum score |
| `S` | signed 18 | This token's score |
| `done` | 1 | High for one cycle, the cycle after `start` |
| `W` | unsigned 8 | Weight; valid with `done`, held until the next `start` |

Scores are integers, so D = M − S is too, and W rounds to 0 once D >= 25.
So the whole exponent is a 25-entry table indexed by D:

| D | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| W | 255 | 199 | 155 | 120 | 94 | 73 | 57 | 44 | 35 | 27 | 21 | 16 | 13 |

| D | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 | 24 | 25+ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| W | 10 | 8 | 6 | 5 | 4 | 3 | 2 | 2 | 1 | 1 | 1 | 1 | 0 |

The original table used e^(−D/2) with 13 entries. Halving the score step was
the largest accuracy gain on real SmolLM attention (`python/smollm_compare.py`).
If `M < S` (should never happen), D is treated as 0, so W = 255. Matches Python
`exp_weight` / `EXP_TABLE`.

## `divider` (`src/divider.v`)

Iterative signed normalization: `result = round(16 * sum_in / denominator)`,
nearest with ties away from zero, as a signed 12-bit code. Uses a 23-bit
shift/subtract division datapath and one rounding/sign cycle. See [divider.md](divider.md) for register widths,
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
make exp_lut   # every D in 0..36 across the score range, plus random pairs
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
