# Single-tile INT8 attention

## How it works

One run computes one attention query of a 64-dimension head (SmolLM-135M
size) over up to 16 tokens. The host sends a token count and a config byte.
The chip reads the 64-component INT8 query, keys and values from an external
SPI flash, computes full 64-dimension Q·K scores, a two-pass softmax and the
weighted average, and returns 4 of the 64 output components as four signed
12-bit results (INT8 plus 4 fractional bits) in eight bytes. Run it with
`chunk = 0..15` for all 64 components. The active top is
`tt_um_attention_head_gf`; no Q/K/V array is stored on the tile.

### Pins

| Pins | Direction | Meaning |
|---|---|---|
| `ui_in[7:0]` | input | Host configuration byte |
| `uo_out[7:0]` | output | Result byte while output-valid; undefined otherwise |
| `uio[0]` | output | Flash MOSI (IO0), always driven |
| `uio[1]` | input | Flash MISO (IO1) |
| `uio[3:2]` | input | Unused |
| `uio[4]` | output | Flash SCK, mode 0 |
| `uio[5]` | output | Flash active-low chip select |
| `uio[6]` | input | Host valid during configuration; host ready during output |
| `uio[7]` | output | Chip ready during configuration; chip valid during output |

Transfers occur on rising `clk` edges when both `uio[6]` and `uio[7]` are high.
After reset, present two configuration bytes in order: `N` (1–16), then
`{chunk[3:0], shift[3:0]}` (chunk in bits 7:4, shift in bits 3:0). Hold each
byte and `uio[6]=1` until `uio[7]=1` on a rising edge. An invalid N is not
accepted (`uio[7]=0`). After the config byte is accepted, the chip starts
without another command. Keep `uio[6]=0` until ready to receive output.

- `chunk` selects output components `4*chunk .. 4*chunk+3` of the 64.
- `shift` scales the raw integer scores to the exponent table: the chip uses
  `D' = round((max_score - score) / 2^shift)` (half up) and weight
  `round(255 * e^(-D'/4))`, so one unit of `D'` should be 0.25 nat. With Q and
  K stored as `q * 2^eq` and `k * 2^ek` (power-of-two INT8 scales) and the
  model's softmax scale `1/sqrt(64) = 1/8`, use `shift = eq + ek + 1`.

The chip then presents eight result bytes: two per component, in component
order. Each pair is the low byte then the high byte of a signed 16-bit value
(the 12-bit result, sign-extended); the output equals that value / 16 in V's
units, so `-2048..2032` means `-128.0..127.0`. For each byte, `uio[7]=1` means
`uo_out` is valid; keep `uio[6]=0` to stall or set it to 1 to accept. The byte
remains stable while stalled. After the eighth transfer, the chip returns to
configuration mode. There is no separate busy/done pin: the host tracks the two
configuration and eight result transfers.

### External memory

Preload signed INT8 bytes, component 0 first:

| Flash byte address | Contents |
|---|---|
| `0x000000 + c` | Q component `c` |
| `0x000400 + 64*t + c` | K token `t`, component `c` |
| `0x000800 + 64*t + c` | V token `t`, component `c` |

Here `0 <= t < N <= 16` and `0 <= c < 64`. Q and K must stay unchanged across
both score passes. Each run reads every Q and K byte twice per token and only
the selected 4-byte chunk of each V row. Bytes between the regions are never read. For full accuracy give each V column
its own power-of-two scale (the chip never mixes columns). The flash must support the standard `0x03` read: one command byte,
three address bytes, then one data byte, all in single-lane SPI mode 0 with no
dummy cycles. MOSI stays driven during the data phase, which a standard
SPI flash ignores. The chip does not issue flash writes, quad-read
commands, or device-specific setup. IO2/IO3 must be held inactive by the board
when not driven (typically WP#/HOLD# pulled high).

`rst_n=0` or `ena=0` aborts the operation and releases chip select. Hold the
condition through a clock edge; restart with N and the config byte afterward. `uio[7]` and
`uo_out` carry no meaning while `rst_n=0`. The host must
be synchronous to `clk` and must not treat an aborted transfer as a result.

## How to test

Run `python3 test/top/run.py` from the repository root. It models the flash at
the SPI pin level and compares complete outputs against the Python integer
model. `make -C test` exercises the same behavior through the Tiny Tapeout
testbench. See [integration status](integration-report.md) for coverage and
remaining checks.

## External hardware

An external SPI NOR flash supporting the `0x03` read, preprogrammed with the
Q/K/V layout above, with compatible I/O voltage. A QSPI part also works if its
WP#/HOLD# (IO2/IO3) pins are pulled high.
