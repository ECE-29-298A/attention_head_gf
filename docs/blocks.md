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
The divider then computes `Oi / L`. Uses four multipliers in parallel; sharing
the `score_mac` multiplier would need extra control logic.

## Verification

Cocotb + Icarus, one module per run, from `test/blocks`:

```sh
make score_mac
make max_reg
make accum
```
