# GF180 one-tile RTL integration report

## Target and hierarchy

Target: Tiny Tapeout `gf180mcuD`, one tile (`info.yaml`). The active top is
`tt_um_attention_head_gf` in `src/project.v`.

```text
tt_um_attention_head_gf
├── attention_controller
│   ├── score_mac ── ripple_add
│   ├── max_reg
│   ├── accum ── ripple_add (two instances)
│   ├── exp_lut
│   └── divider
└── qspi_read_adapter
    └── qspi_byte
        └── spi_multi_io_byte (LANES=4)
```

`ospi_byte`, `full_adder`, and the incomplete `multiplier` and `addr_gen`
sources are not part of this selected top. The existing `qspi_byte` is reused
without internal changes. The active attention datapath remains four signed
INT8 components and 1–16 tokens.

## Boundary contracts checked

| Boundary | Contract and integration decision |
|---|---|
| Host to top | `ui_in` carries N, Q0..Q3. `uio[6]` is host valid for configuration and host ready for output; `uio[7]` is chip ready/valid. Transfers occur on rising `clk` when both are high. Invalid N cannot handshake. |
| Top to controller | N is five bits; Q is 32 bits with Q0 in bits 7:0. A one-cycle `start` is issued only after all five configuration bytes are captured and `start_ready` is high. Four signed output bytes pass through with `out_valid/out_ready` backpressure. |
| Controller to adapter | The controller holds its 16-bit byte address while `mem_req_valid` waits. The adapter accepts only when idle, allows one outstanding read, and returns one `rsp_valid` pulse in a later cycle. `mem_write` and `mem_wdata` are unused constants from the read-only controller. |
| Adapter to byte engine | Each controller byte read sends `0x03`, a 24-bit address, and one receive byte. The adapter starts a byte only when `ready`, waits for `done`, and sets `last` only on the data byte; CS stays asserted between bytes. |
| Byte engine to flash pins | Mode 0, MSB first, single-lane transfers: IO0 drives command/address, IO1 receives data. IO2/IO3 remain released and require inactive pull-ups for a flash that uses WP#/HOLD# there. SCK and CS_n occupy fixed outputs. |
| Clock and reset | All controller, wrapper, and adapter state uses `clk`; the core and wrapper have synchronous active-low reset. The existing SPI byte engine releases CS asynchronously when `rst_n`/`ena` goes low. Hold reset/disable through a clock edge to reset the rest of the hierarchy. |

The controller's original handshake and arithmetic cycle sequence are unchanged.
The QSPI adapter uses `FLASH_BASE=0` in the top, so K occupies flash bytes
`0x00..0x3f` and V `0x40..0x7f`. The flash must be preloaded and K must remain
stable across both passes. See [pin protocol](pin-protocol.md) for host timing.

## Changes

- Replaced the template adder top with the host configuration, QSPI, and output
  wrapper; selected it and its sources in `info.yaml` and `test/Makefile`.
- Added `qspi_read_adapter` to bridge ready/valid byte requests to five SPI
  byte transfers per flash read.
- Added a top-level pin/flash Cocotb test and made it the default Tiny Tapeout
  RTL test. Updated the configured testbench instance.
- Corrected stale SPI source paths in its tests and GF180 area script. The
  Tiny Tapeout and block-test Makefiles now use relative source paths so the
  checkout works when a parent directory contains spaces.
- Replaced the template README and datasheet with the actual pin protocol.

## Verification

Run from the repository root:

| Command | Result |
|---|---|
| `iverilog -g2012 -s tt_um_attention_head_gf ...` with all 11 selected RTL files | Elaborates with no unresolved modules. |
| `verilator --lint-only -Wall -Wno-fatal --top-module tt_um_attention_head_gf ...` | No latch, multiple-driver, width, or missing-module finding. See residual warnings below. |
| `python3 test/top/run.py` | Passed pin-level `0x03` flash model and Python-model results for N=1, 2, 16; exact K/K/V read order; invalid N; output stalls; back-to-back queries; reset and `ena` abort during SPI transfer. Bounded at 30,000 clocks per output. |
| `make -C test` | Same top test passed through the configured Tiny Tapeout testbench. |
| `make -C test/spi_byte test lint` | Both QSPI and OSPI byte engines passed their existing Cocotb and Verilog tests and lint after path correction. |
| `make -C test/blocks score_mac`, `max_reg`, `accum`, `exp_lut` (results checked after each) | All four block-level Cocotb regressions passed. |
| `python3 test/controller/run.py`; `python3 test/controller/cocotb/run.py`; `python3 test/divider/run.py`; `pytest -q python/test_attention_model.py` | Passed after integration: seven controller configurations with 139 cases each, two controller Cocotb tests, 1,088,022 divider vectors, and three Python-model tests. No arithmetic module was changed. |

Verilator still reports a filename/module-name warning for Tiny Tapeout's
required `project.v`, the intentionally unused final carry in `ripple_add`, and
mixed synchronous/asynchronous use of the shared reset (the existing byte
engine intentionally releases CS asynchronously). None indicates a latch or
multiple driver. This reset distinction is exercised by the abort tests.

## Remaining defects and unverified assumptions

- Local GF180 synthesis and place and route are recorded in the
  [integration log](../INTEGRATION_LOG.md). The shuttle LibreLane flow and the
  GDS-level DRC/LVS checks remain open.
- The read adapter deliberately uses the common `0x03` single-lane command on
  a QSPI memory. It does not yet use four data lanes, configure the flash, or
  implement vendor-specific dummy cycles. Confirm the selected flash's voltage,
  command support, and pin timing on the actual board.
- The host must preload flash K/V, be synchronous to `clk`, hold each input
  byte until accepted, and restart after reset or `ena` abort. There is no
  on-chip flash programming, CDC, timeout, or error/status channel. The flash
  pin test uses an ideal behavioral model, not a specific chip's timing model.
- The historical `docs/blocks.md`, `docs/controller.md`, `docs/divider.md`,
  and INT4 sequence pages do not describe the current INT8 widths/latencies.
  This report and `src/` describe the selected integrated hierarchy; those
  pages need a numerical documentation refresh.
- `info.yaml` retains a blank author as requested. Tiny Tapeout requires a
  project author before submission.
- The `codex-reference/` one-tile physical reports concern a separate SKY130
  `norm_odd` implementation; they cannot establish GF180 fit for this design.
