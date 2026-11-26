# Single-tile INT8 attention

## How it works

One run computes one attention query of a 64-dimension head (SmolLM-135M
size) over up to 16 tokens and returns 2 of the 64 output components. The host
sends a token count and a config byte. The chip reads signed INT8 Q, K and V
bytes from an external SPI flash as one continuous stream (the tape), computes
full 64-dimension Q·K scores, a two-pass softmax and the weighted average, and
returns two signed 12-bit results (INT8 plus 4 fractional bits) in four bytes.
A whole head is 32 runs: one fresh run and 31 continue runs. The active top is
`tt_um_attention_head_gf`; no Q/K/V array is stored on the tile.

### Pins

| Pins | Direction | Meaning |
|---|---|---|
| `ui_in[7:0]` | input | Host configuration byte |
| `uo_out[7:0]` | output | Result byte while output-valid; zero otherwise |
| `uio[0]` | output | Flash MOSI (IO0); always driven, low outside the command |
| `uio[1]` | input | Flash MISO (IO1) |
| `uio[3:2]` | input | Unused |
| `uio[4]` | output | Flash SCK, mode 0, `clk`/2 while reading |
| `uio[5]` | output | Flash active-low chip select |
| `uio[6]` | input | Host valid during configuration; host ready during output |
| `uio[7]` | output | Chip ready during configuration; chip valid during output |

Transfers occur on rising `clk` edges when both `uio[6]` and `uio[7]` are high.
After reset, present two configuration bytes in order:

1. Count byte `N` (1–16).
2. Config byte `{cont, 3'b000, shift[3:0]}`.

Hold each byte and `uio[6]=1` until `uio[7]=1` on a rising edge. A count byte
outside 1–16 is not accepted (`uio[7]=0`). After the config byte is accepted, the chip starts
without another command. Keep `uio[6]=0` until ready to receive output.

- `cont = 0` is a fresh run: the chip restarts the flash read at address 0,
  reads pass 1 to find the maximum score, then reads one pass-2 block.
- `cont = 1` is a continue run: the chip keeps the maximum and the open flash
  read and consumes the next pass-2 block. Use it for the remaining chunks of
  the same query, with the same `N` and `shift`. A continue run before any
  fresh run reads garbage.
- `shift` scales the raw integer scores to the exponent table: the chip uses
  `D' = round((max_score - score) / 2^shift)` (half up) and weight
  `round(255 * e^(-D'/4))`, so one unit of `D'` should be 0.25 nat. With Q and
  K stored as `q * 2^eq` and `k * 2^ek` (power-of-two INT8 scales) and the
  model's softmax scale `1/sqrt(64) = 1/8`, use `shift = eq + ek + 1`.

The chip then presents four result bytes: two per component, in component
order. Each pair is the low byte then the high byte of a signed 16-bit value
(the 12-bit result, sign-extended); the output equals that value / 16 in V's
units, so `-2048..2032` means `-128.0..127.0`. For each byte, `uio[7]=1` means
`uo_out` is valid; keep `uio[6]=0` to stall or set it to 1 to accept. The byte
remains stable while stalled. After the fourth transfer, the chip returns to
configuration mode. There is no separate busy/done pin: the host tracks the two
configuration and four result transfers.

### External memory: the tape

The chip never generates an address. It sends one standard `0x03` read at
address 0 (single-lane SPI mode 0, no dummy cycles) and then clocks bytes out
in order, so the host writes the memory in the order the chip consumes it.
`tape()` in `python/src/attention_model.py` builds this image:

| Block | Bytes | Contents |
|---|---|---|
| Score row `t` | 128 | `Q[0], K[t][0], Q[1], K[t][1], … Q[63], K[t][63]` |
| Pass 1 | `128·N` | Score rows `0 … N-1` |
| Pass-2 block for chunk `c` | `130·N` | For each `t`: score row `t`, then `V[t][2c], V[t][2c+1]` |
| Tape | | Pass 1, then one pass-2 block per run, in run order |

Here `0 <= t < N <= 16`. Which two output components a run produces is decided
only by which V bytes the host put in that pass-2 block. A full head (32
chunks) at `N = 16` is 68,608 bytes. For full accuracy give each V column its
own power-of-two scale (the chip never mixes columns).

The flash stays selected, with SCK idle low, between runs and while the host
reads results. `rst_n=0` or `ena=0` aborts the operation and releases chip
select; the host must do this before it rewrites the memory for the next
query. Hold the condition through a clock edge; restart with N and the config
byte afterward. The chip does not issue flash writes, quad-read commands, or
device-specific setup. The host must be synchronous to `clk` and must not treat
an aborted transfer as a result.

## How to test

Run `python3 test/top/run.py` from the repository root. It models the flash at
the SPI pin level and compares complete outputs against the Python integer
model. `make -C test` exercises the same behavior through the Tiny Tapeout
testbench. See [integration status](integration-report.md) for coverage and
remaining checks.

## External hardware

An external SPI memory that answers the `0x03` read, loaded with the tape above,
with compatible I/O voltage. On a flash part, hold WP#/HOLD# (IO2/IO3) high.
The tape is rewritten for every query, so an SPI RAM or a host that emulates
the memory suits it better than a NOR flash that must be erased each time.
