# Single-tile INT8 attention

## How it works

The host supplies a token count and a four-byte signed INT8 query. The chip
reads K and V from an external QSPI flash, calculates a two-pass softmax-weighted
average, and returns four signed 12-bit results (INT8 plus 4 fractional bits)
as eight bytes. The active top is
`tt_um_attention_head_gf`; no K/V array is stored on the tile.

### Pins

| Pins | Direction | Meaning |
|---|---|---|
| `ui_in[7:0]` | input | Host configuration byte |
| `uo_out[7:0]` | output | Result byte while output-valid; zero otherwise |
| `uio[3:0]` | bidirectional | QSPI flash IO0–IO3; current `0x03` reads use IO0/IO1 only |
| `uio[4]` | output | QSPI SCK, mode 0 |
| `uio[5]` | output | QSPI active-low chip select |
| `uio[6]` | input | Host valid during configuration; host ready during output |
| `uio[7]` | output | Chip ready during configuration; chip valid during output |

Transfers occur on rising `clk` edges when both `uio[6]` and `uio[7]` are high.
After reset, present five configuration bytes in order: `N` (1–16), then
`Q0`, `Q1`, `Q2`, `Q3`. Hold each byte and `uio[6]=1` until `uio[7]=1` on a rising
edge. An invalid N is not accepted (`uio[7]=0`). After Q3 is accepted, the chip
starts without another command. Keep `uio[6]=0` until ready to receive output.

The chip then presents eight result bytes: two per component, in component
order. Each pair is the low byte then the high byte of a signed 16-bit value
(the 12-bit result, sign-extended); the output equals that value / 16 in V's
units, so `-2048..2032` means `-128.0..127.0`. For each byte, `uio[7]=1` means
`uo_out` is valid; keep `uio[6]=0` to stall or set it to 1 to accept. The byte
remains stable while stalled. After the eighth transfer, the chip returns to
configuration mode. There is no separate busy/done pin: the host tracks the five
configuration and eight result transfers.

### External memory

Preload four signed INT8 bytes per token, component 0 first:

| Flash byte address | Contents |
|---|---|
| `0x000000 + 4*t + c` | K token `t`, component `c` |
| `0x000040 + 4*t + c` | V token `t`, component `c` |

Here `0 <= t < N <= 16` and `0 <= c < 4`. K must stay unchanged across both
score passes. The flash must support the standard `0x03` read: one command byte,
three address bytes, then one data byte, all in single-lane SPI mode 0 with no
dummy cycles. The current adapter does not issue flash writes, quad-read
commands, or device-specific setup. IO2/IO3 must be held inactive by the board
when not driven (typically WP#/HOLD# pulled high).

`rst_n=0` or `ena=0` aborts the operation and releases chip select. Hold the
condition through a clock edge; restart with N and Q afterward. The host must
be synchronous to `clk` and must not treat an aborted transfer as a result.

## How to test

Run `python3 test/top/run.py` from the repository root. It models the flash at
the SPI pin level and compares complete outputs against the Python integer
model. `make -C test` exercises the same behavior through the Tiny Tapeout
testbench. See [integration status](integration-report.md) for coverage and
remaining checks.

## External hardware

An external QSPI flash preprogrammed with the K/V layout above, with compatible
I/O voltage and pull-ups on the flash's inactive IO2/IO3 controls.
