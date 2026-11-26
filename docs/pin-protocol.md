# Single-tile INT8 attention

## How it works

One run computes one attention query of a 64-dimension head (SmolLM-135M
size) over up to 16 tokens and returns 8 of the 64 output components. The host
writes a config frame over SPI. The chip reads signed INT8 Q, K and V
bytes from an external quad SPI flash as one continuous stream (the tape), computes
full 64-dimension Q·K scores, a two-pass softmax and the weighted average, and
returns eight signed 12-bit results (INT8 plus 4 fractional bits) in eight SPI
frames. A whole head is 8 runs: one fresh run and 7 continue runs. (The RTL
parameter `OUTPUTS` = 8, 4 or 2 sets the outputs per run; the chip uses 8.) The active
top is `tt_um_attention_head_gf`; no Q/K/V array is stored on the tile.

### Pins

| Pins | Direction | Meaning |
|---|---|---|
| `ui_in[0]` | input | Host SCK, SPI mode 0 (CPOL = 0, CPHA = 0) |
| `ui_in[1]` | input | Host MOSI (COPI), MSB first |
| `ui_in[2]` | input | Host CS#, active low |
| `ui_in[7:3]` | input | Unused |
| `uo_out[0]` | output | Host MISO (CIPO), MSB first; always driven |
| `uo_out[1]` | output | DRDY: high while a result is ready to read |
| `uo_out[7:2]` | output | Always 0 |
| `uio[0]` | output | Flash CS0#, active low |
| `uio[1]` | in/out | Flash IO0: output only for the command and address, then input |
| `uio[2]` | input | Flash IO1 |
| `uio[3]` | output | Flash SCK, mode 0 |
| `uio[4]` | input | Flash IO2 |
| `uio[5]` | input | Flash IO3 |
| `uio[6]` | output | CS1# (Pmod RAM A), always high |
| `uio[7]` | output | CS2# (Pmod RAM B), always high |

`uio` follows the [Tiny Tapeout QSPI Pmod](https://github.com/mole99/qspi-pmod).
The Pmod has no pull-ups on CS1#/CS2#, so the chip drives them high to keep both
RAMs off the shared IO lines.

### Host interface: SPI target

The chip is an SPI target in mode 0: the host changes MOSI after a falling SCK
edge (or before the first rising edge), and both sides sample on rising edges.
Every frame is 16 bits, MSB first, between a falling and a rising edge of CS#.
The host's SCK does not need to be related to `clk`; the chip passes SCK and
CS# through 2-flop synchronizers.

1. **Config frame.** Clock `0000000, cont, shift[3:0], N-1[3:0]` (`config_frame()`
   in `python/src/attention_model.py`). The chip keeps the last 9 bits clocked
   in. The run starts on the CS# rising edge. Every 4-bit `N-1` (N = 1 to 16)
   and every `shift` is valid.
2. **Result frames.** Wait until DRDY is high (about 33k `clk` for a fresh run
   at N = 16, about 17k for a continue run, about 25 to 32 `clk` between
   components), then clock 16 bits:
   bits 15 to 4 on MISO are the signed 12-bit result, the last 4 are 0
   (`decode_result_frame()`). MOSI is ignored. The CS# rising edge ends the
   read; the chip then divides the next component.
3. Repeat for components 1 to 7, in order. After the eighth read's CS# rise
   the chip is idle and takes the next config frame.

A frame that ends while DRDY is high is a result read; there is no command
byte. A config frame sent while the chip is busy, with DRDY low for the whole
frame and for `t_CSW` after it, is ignored. MISO is driven at all times, so the
chip must be the only target on its MISO line.

**Timing** (one `clk` is 100 ns at 10 MHz). The chip acts on an SCK or CS#
edge within 3 `clk`; the fourth `clk` of every rule covers synchronizer
metastability and pad delays.

| Rule | Minimum |
|---|---|
| SCK high and SCK low, each (so SCK ≤ `clk`/8, 1.25 MHz at 10 MHz) | 4 `clk` |
| CS# falling edge to the first SCK rising edge | 4 `clk` |
| Last SCK falling edge to CS# rising edge | 0 (SCK must be low before CS# rises) |
| `t_CSW`: CS# high after its rising edge, before the next CS# fall, before sampling DRDY and before a reset | 4 `clk` |
| Reset: `rst_n` (or `ena`) low, with CS# high | 3 `clk` |

MISO is valid before the first rising SCK edge and changes at most 3 `clk`
(plus pad delay) after each falling edge. MOSI must hold from each rising SCK edge until the
falling edge. DRDY can stay high for up to 3 `clk` after the CS# rise that
ends a read, so the host reads DRDY only after `t_CSW`.

### Config fields

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

Results come in component order. Each is a signed 12-bit value; the output
equals that value / 16 in V's units, so `-2048..2032` means `-128.0..127.0`.

### External memory: the tape

The chip never generates an address. A fresh run sends one Fast Read Quad
Output (`0x6B`) at address 0 and then clocks the data out in order, so the host
writes the memory in the order the chip consumes it:

1. CS0# goes high for 1 `clk`, which ends any open read, then falls.
2. `0x6B` and the 24-bit address 0 on IO0, MSB first, SCK = `clk`/4 (high 1
   `clk`, low 3). IO0 changes 2 `clk` before each rising edge.
3. 8 dummy clocks. The chip releases IO0 after the last address bit, 8 SCK
   cycles before the flash drives it; IO1 to IO3 are always inputs.
4. Data on IO3..IO0, high nibble first (IO3 = bit 7, IO0 = bit 4, then bits 3
   to 0). Each SCK rise samples a nibble and the chip uses its 4 bits on the
   next 4 `clk`, so SCK = `clk`/4 (high 1 `clk`) and the flash has 3 `clk` from
   each falling edge to its next sample.

A run ends right after its last nibble is sampled, with SCK low and CS0# low.
A continue run starts by sampling the next nibble, which the flash has held on
IO3..IO0 since. The flash sees exactly 40 + 2·(bytes read) rising SCK edges.

`tape()` in `python/src/attention_model.py` builds the image:

| Block | Bytes | Contents |
|---|---|---|
| Score row `t` | 128 | `Q[0], K[t][0], Q[1], K[t][1], … Q[63], K[t][63]` |
| Pass 1 | `128·N` | Score rows `0 … N-1` |
| Pass-2 block for chunk `c` | `136·N` | For each `t`: score row `t`, then `v_planes(V[t][8c : 8c+8])` (8 bytes) |
| Tape | | Pass 1, then one pass-2 block per run, in run order |

Q and K bytes are signed INT8, read MSB first. The eight V values of a token,
`c0 … c7 = V[t][8c] … V[t][8c+7]`, are stored as 8 bytes by bit plane
(`v_planes()`): byte `i` holds bit `7-i` of `c0, c1, … c7`, MSB first, so the
stream is `c0b7 c1b7 … c7b7 c0b6 … c7b0`. The chip takes one bit per `clk` and
its eight accumulators take turns each `clk`, so every V bit goes straight to
its accumulator. (With `OUTPUTS` = 4 or 2 the same rule gives 4 or 2 bytes.)

Here `0 <= t < N <= 16`. Which eight output components a run produces is decided
only by which V values the host put in that pass-2 block. A full head (8
chunks) at `N = 16` is 19,456 bytes. For full accuracy give each V column its
own power-of-two scale (the chip never mixes columns).

The flash stays selected, with SCK idle low, between runs and while the host
reads results. `rst_n=0` or `ena=0` aborts the operation and releases chip
select; the host must do this before it rewrites the memory for the next
query. Hold it for at least 3 `clk` with CS# high (the same rule as the
power-up reset, which also clears the SPI synchronizers); restart with a
config frame afterward. The chip issues no command other than `0x6B`: no
writes, no status reads and no Quad Enable setup. The host must not treat an
aborted transfer as a result.

## How to test

Run `python3 test/top/run.py` from the repository root. It models the flash at
the SPI pin level, drives the host SPI frames on timers unrelated to `clk`
(at the 4-`clk` limit, edge-aligned, jittered and slow), and compares complete
outputs against the Python integer model. `make -C test` exercises the same behavior through the Tiny Tapeout
testbench. See [integration status](integration-report.md) for coverage and
remaining checks.

## External hardware

The Tiny Tapeout QSPI Pmod with its W25Q128JV flash, loaded with the tape
above. When reset is released the flash must be in standard SPI mode: not in
QPI mode and not in a `0xEB` continuous-read mode, because the chip sends its
command on IO0 only. The `-IQ`/`-JQ` parts ship with the Quad Enable bit set, which the chip
relies on; on other parts the host sets QE when it programs the tape. Any flash
that answers `0x6B` with 8 dummy clocks and IO2/IO3 as data works the same way.
The Pmod's APS6404L RAMs are not usable as the memory: they need CS# released
every few microseconds for refresh, and the chip holds CS0# low for a whole run.
The tape is rewritten for every query, so a host that emulates the flash avoids
erasing it each time.
