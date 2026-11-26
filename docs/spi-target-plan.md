# Plan: SPI target host interface and wider output ring

Status: planned, not implemented. Branch `spi-target-io`, based on `fast-tape`
(`4348176`).

This branch makes two changes, done and measured one after the other so the
area cost of each is known:

1. **SPI target host interface:** replace the parallel host bus with a
   standard SPI target.
2. **Wider output ring:** compute 4 or 8 outputs per run instead of 2, with
   the ring width as a parameter.

The external Q/K/V memory side is unchanged by both: it is already a standard
SPI controller issuing a plain `0x03` read.
(Superseded: a later change reads the tape with a quad `0x6B` read on the
TT QSPI Pmod pins; see `docs/pin-protocol.md` and `INTEGRATION_LOG.md` §11.)

## Baseline

`fast-tape` `4348176`, LibreLane 3.0.14 harden on gf180mcuD, run on 2026-11-25:

| Metric | Value |
|---|---|
| Cell area after synthesis | 33,121 µm² |
| Cell area after design repair | 37,255 µm² |
| Cell area after clock tree synthesis (final) | 38,493 µm² |
| Core utilization | 74.1% of 51,967 µm² |
| Standard cells / flip-flops | 1,800 / 204 |
| Setup / hold worst slack | +35.3 ns / +0.15 ns |
| DRC / LVS / antenna | 0 / 0 / 0 |
| Max slew violations | 162 (tt corner), 269 (ss 125 °C) |
| Max cap / fanout violations | 1 / 3 |
| Cycles per head at N = 16 | about 1.10M (32 runs of 2 outputs) |
| Tape size per head at N = 16 | 68,608 bytes |

The slew, capacitance and fanout warnings already exist on `fast-tape` and
are separate from this branch. The likely cause is `MAX_FANOUT_CONSTRAINT`
of 20 combined with the 10% design repair margins in `src/config.json`.

## Change 1: SPI target host interface

### Goal

Replace the 8-bit parallel host interface (`ui_in[7:0]`, `uo_out[7:0]`, and
the `uio[6]`/`uio[7]` handshake) with a serial interface that is a defined
standard, at minimum area and with the simplest implementation.

### Choice of standard: SPI target (slave), mode 0

| Standard | Logic needed beyond the data registers | Rough cost |
|---|---|---|
| **SPI target** | Synchronizers on SCK/CS#/MOSI and edge detection | **about +8 flops** |
| I2C target | Start/stop detection, 7-bit address match, ACK, bit counter, open-drain SDA, glitch filter | +25 to 30 flops |
| UART | Baud-rate counter, start-bit search with mid-bit sampling, bit counter, start/stop framing, for both TX and RX | +25 flops or more |

SPI defines the signals, the clock mode and the frame (chip select). The
payload is device-defined on every SPI part, so no command or register map
is needed beyond the frames below.

### Pins

| Pin | Signal | Use |
|---|---|---|
| `ui_in[0]` | SCK | Host clock, mode 0 (CPOL=0, CPHA=0) |
| `ui_in[1]` | MOSI (COPI) | Config bits from the host, MSB first |
| `ui_in[2]` | CS# | Active low; its rising edge ends a frame |
| `uo_out[0]` | MISO (CIPO) | Result bits to the host, MSB first |
| `uo_out[1]` | DRDY | High when a result is ready to read |

DRDY works like the data-ready pin on SPI ADCs (for example TI's ADS1220). It
is the controller's existing "result ready" state, with no extra logic.

`uio[0,1,4,5]` stay as the flash SPI controller. `uio[2,3,6,7]` become unused.
The other `ui_in` and `uo_out` bits are unused, and the unused `uo_out` bits
are tied to 0.

### Host sequence

1. **Write the config:** pull CS# low, clock 16 bits
   `0000000, cont, shift[3:0], N-1[3:0]`, then raise CS#. The run starts on
   that rising edge.
2. **Read each component:** wait for DRDY (about 66k `clk` cycles for a
   fresh run at N = 16). Pull CS# low and clock 16 bits; bits 15 to 4 are the
   signed 12-bit result and the last 4 read 0. Raise CS#. The chip then
   divides the next component, which takes about 25 `clk` cycles.
3. **Repeat** for every component of the run (2 today, 4 or 8 after
   change 2). After the last read the chip goes idle and is ready for the
   next config write.

A config write sent while the chip is busy is ignored. `rst_n = 0` or
`ena = 0` aborts a run, as it does today. The meaning of `cont` and `shift`
is unchanged (see `pin-protocol.md`).

Timing limit: SCK must be at most `clk`/8 (1.25 MHz at `clk` = 10 MHz), with
the high and low phases each at least 4 `clk` periods. The host's SCK does
not need to be related to `clk`.

### Hardware

- **Synchronizers:** SCK, CS# and MOSI each pass through 2 flops into `clk`.
  SCK and CS# get 1 more flop each to detect edges. That's about 8 flops, and
  the only real cost of this change. MOSI goes through the same 2 stages as
  SCK, so the bit stays aligned with its clock edge.
- **Config in:** the existing config registers become one 9-bit shift chain
  `{cont, shift[3:0], last[3:0]}`, where `last = N - 1`. It shifts on each
  synchronized SCK rising edge while CS# is low and the chip is idle. Only the
  last 9 bits clocked in are kept. Sending N-1 means every 4-bit value is
  valid, which removes the 1 to 16 range check and the `token_count - 1`
  decrementer.
- **Result out:** the divider's existing 12-bit `result` register becomes a
  shift register. MISO is `result[11]`, and the register shifts left, taking
  in 0, on each synchronized SCK falling edge while CS# is low and DRDY is
  high. That's 12 small muxes and no new flops.
- **Start and advance:** a synchronized CS# rising edge
  - while idle, starts a run with the shifted config;
  - while DRDY is high, fires the controller's existing `OUTPUT` handshake
    once per component instead of once per byte;
  - otherwise does nothing.

**Removed:**

- The `stage` state machine in `project.v` (2 flops) and the `LAUNCH` cycle.
- The count range check, the `cfg_ready`/`cfg_accept` logic, and the
  decrementer.
- The `high_byte` flop, the byte mux with sign extension, and the 8 AND
  gates on `uo_out`.

### Estimate

About +5 flops (204 to about 209): 8 for synchronizers, minus 1 config bit,
2 stage bits and `high_byte`. Logic roughly breaks even, since the removed
byte mux and decrementer offset the 12 new shift muxes. Cell area is
expected within about 1% of the baseline. This is an estimate, to be
confirmed by the LibreLane harden.

The synchronizers are the price of real SPI: they make the interface work
with a host whose SCK is unrelated to `clk`, as standard SPI hosts expect.

### Steps

1. `src/project.v`: add the SPI target (synchronizers, config shift chain,
   MISO and DRDY) and remove the stage machine.
2. `src/divider.v`: add a `SHIFT_OUT` parameter that makes `result`
   shiftable. With `SHIFT_OUT = 0` the divider works as today, so
   `test/divider` keeps passing.
3. `src/attention_controller.sv`: take `last` (N-1) directly and fire the
   `OUTPUT` handshake once per component.
4. `python/src/attention_model.py`: add helpers that build the config frame
   and decode a result frame.
5. Tests:
   - add an SPI host model to `test/top/test_top_qspi.py`, with SCK slower
     than and unrelated to `clk`, including SCK/`clk` ratios at and above
     the limit;
   - update `test/controller/tb_controller.sv`.
6. Docs: update `docs/pin-protocol.md` and the `info.yaml` pinout, and add an
   `INTEGRATION_LOG.md` section.
7. Check: run all regressions and the LibreLane harden, and compare against
   the baseline.

## Change 2: wider output ring (4 or 8 outputs per run)

### Why

Each run computes all N scores again to produce only 2 outputs, so a head
takes 32 runs and most of the time goes to re-reading Q and K. Producing more
outputs per run cuts the number of runs and the re-reads.

These are outputs per run, not multipliers. All output sums share the one
shift-and-add adder in `mac_unit.v`, as on `main`. Parallel multipliers or
separate score and accumulate adders gain nothing here: the single SPI line
delivers one bit every 2 clocks, one adder keeps up with that, and scoring
and accumulating never run in the same cycle.

### Options at N = 16

| Outputs per run | Runs per head | Tape size | Cycles per head | Speed | Extra flops |
|---|---:|---:|---:|---:|---:|
| 2 (baseline) | 32 | 68,608 B | about 1.10M | 1× | none |
| 4 (as on `main`) | 16 | 35,840 B | about 0.57M | about 1.9× | about +42 |
| 8 | 8 | 19,456 B | about 0.31M | about 3.5× | about +124 |

Each added output is one 20-bit sum; the phase counter and output index also
widen. Cycle counts assume the V bit order below; they are estimates from the
tape length at 16 clocks per byte.

### Area

| Design | Cell area | Core used |
|---|---:|---:|
| Baseline, 2 outputs (measured) | 38,493 µm² | 74% |
| 4 outputs plus SPI target, standard cells | about 41.5k µm² | about 80% |
| 8 outputs plus SPI target, standard cells | about 48k µm² | about 92%, likely fails placement |
| 8 outputs plus SPI target, custom layout saving 40% | about 29k µm² | about 55% |
| 8 outputs plus SPI target, custom layout saving 20% | about 38k µm² | about 74% |

All rows except the baseline are estimates (flops at about 64 µm² each,
plus muxes and clock buffers). An earlier shuttle run failed placement at
96 to 99% core use, so 8 outputs only fits with custom layout. It fits if
custom layout saves about 15% or more.

Custom layout saves the most on logic and wiring and less on flops. With 8
outputs the flops are about half the area, so 25 to 30% overall may be more
realistic than 40%. That still gives about 66 to 69% core use.

### Plan

- Make the ring width a parameter, `OUTPUTS` = 2, 4 or 8.
- **Fallback:** harden 4 outputs with standard cells. It is expected to fit.
- **Target:** 8 outputs, with the output ring and adder in custom layout and
  the control logic left as standard cells. The added area is almost all
  that regular datapath (eight 20-bit registers in a ring feeding one 22-bit
  adder), which is where hand layout beats standard cells most. The ring
  advances every clock, so a hand-built register chain with short
  neighbour-to-neighbour wiring avoids most of the buffering and slew repair
  the standard-cell flow adds.

### V bit order on the tape

(Superseded: with the quad read the tape arrives at 1 bit per clock, so the V
bits are in plain bit-plane order with no stalls and the cycle counts above are
about halved; see `INTEGRATION_LOG.md` §12.)

Today the chip holds SCK so each V bit waits for its sum to reach the adder.
With 8 sums a bit could wait up to 8 clocks, which would cut the speedup to
about 3×. The host decides the tape order, so the fix is nearly free:
interleave the V bits across components in the order 0, 2, 4, 6, 1, 3, 5, 7.

The ring turns every clock and a bit arrives every 2 clocks, so consecutive
bits land 2 positions apart: 0, 2, 4, 6 and then 0 again. The chip therefore
holds SCK for one extra clock after every 4 bits, which moves the next 4 bits
onto 1, 3, 5, 7. That costs 9 clocks per 4 V bits instead of 8, about 12%
more time on V, which is a small part of the tape (8 of 136 bytes per
token). The 4-output version uses the order 0, 2, 1, 3, with one extra clock
after every 2 bits.

### Changes

1. `src/mac_unit.v`: an `OUTPUTS`-deep ring of 20-bit sums on the one shared
   adder.
2. `src/attention_controller.sv`: phase counter and output index of
   `log2(OUTPUTS)` bits; `OUTPUTS` V bytes per token per chunk; the new V bit
   order; `OUTPUTS` divisions and SPI result reads per run.
3. `python/src/attention_model.py`: `tape()` builds chunks with `OUTPUTS` V
   components per token in the interleaved bit order.
4. Tests: run the controller and top tests at `OUTPUTS` = 2, 4 and 8.
5. Measure: run synthesis alone at 4 and 8 outputs to replace the estimates
   above, then harden 4 outputs with standard cells.
6. Docs: `docs/pin-protocol.md`, `info.yaml` and an `INTEGRATION_LOG.md`
   section.

### Risks to check before committing to 8 outputs

1. **Shuttle rules:** confirm the Tiny Tapeout GF180 shuttle accepts custom
   layout. Tiny Tapeout supports analog projects on other processes; the
   current GF180 rules still need checking.
2. **Verification:** custom cells have no timing library, so the flow's
   timing and slew checks cannot cover that part. LVS against the netlist and
   DRC still apply. Either build a timing library for the custom cells or
   check margins by hand. The 100 ns clock leaves +35 ns of setup slack.
3. **Savings estimate:** the 40% figure is historical. Measure the custom
   ring against the standard-cell ring early.

## Open points

- MISO is driven at all times on `uo_out[0]`, which suits a host with a
  single device. Tri-stating it while CS# is high, for a shared bus, would
  need a `uio` pin with `oe = CS# low`.
- The harden flow needs a path without spaces and a git clone with a `tt/`
  folder, because `tt_tool` fails on `2B ECE` in the path.
