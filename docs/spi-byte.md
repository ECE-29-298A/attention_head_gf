# Minimal QSPI and OSPI byte engines

This repository contains two synthesizable master blocks: `qspi_byte` (x1/x4) and
`ospi_byte` (x1/x8). Both use `spi_multi_io_byte`, with the lane count fixed at
elaboration. The blocks implement SPI mode 0, single data rate, most significant
bit first. Each byte takes eight, two, or one SCK periods in x1, x4, or x8 mode.
SCK is half the `clk` frequency during a byte. There is one `clk` of setup before
the first SCK rising edge and one `clk` of hold after the last falling edge.

## Interface

Apply a one-cycle `start` pulse while `ready` is high. The block samples
`tx_data`, `wide`, `tx_en`, and `last` on that edge. `done` pulses for one `clk`
when `rx_data` is complete and `ready` returns high. `last=0` keeps `cs_n` low
for another byte; `last=1` releases it after this byte. A transaction can mix
x1 and wide bytes. Reset releases chip select, including if a transaction was
left open.
`rx_data` is only valid when `done` is high; its register is not reset.

`wide=0` uses conventional SPI: transmit on IO0 and sample on IO1. `wide=1`
uses all four or eight IO lanes. Set `tx_en=1` to drive the output lanes, or
`tx_en=0` to release them and sample input. `io_o` and `io_oe` are separate so
the top-level can instantiate its target technology's bidirectional pad cells.
In x1 mode, `rx_data` records IO1 even during transmit. In wide mode, it records
all input lanes; ignore `rx_data` for output transfers.

For example, a standard flash JEDEC ID read is a transmitted x1 `0x9f` byte
with `last=0`, followed by three received x1 bytes, with `last=1` on the third.
Flash-specific commands, addressing, dummy cycles, mode configuration, and
write-enable sequencing belong in the caller. Dummy byte periods can be sent
as receive transfers while keeping chip select low. The blocks do not implement
DDR/DTR, DQS, a clock divider, FIFOs, or memory-mapped access.

The hardware reuses one 8-bit shifter for transmit and receive, with one
sample register as wide as the IO bus, a three-bit down counter, and a small
control state machine. Datapath and command latch registers are unreset because
each is loaded before use; only control outputs and state need reset. Both
wrappers elaborate the same RTL. No claim of absolute minimum silicon area is
made without a target library and synthesis constraints.

Run `make -C test/spi_byte test` for cocotb and Verilog simulations on both wrappers.
`make -C test/spi_byte test-cocotb` runs only the cocotb cycle and pin checks
(`python3 -m pip install -r test/requirements.txt` if needed).
Run `make -C test/spi_byte lint` for Verilator lint.
See [GF180 area assessment](spi-byte-gf180-area.md) for the pinned cell library,
reproduction command, and measured sequential-cell area comparison.

## Source selection

[LiteSPI](https://github.com/litex-hub/litespi) is a permissively licensed,
configurable x1/x4/x8 core, but its PHY and system interface are broader than
the requested basic byte interface. The compact
[spi_mem_programmer](https://github.com/sergachev/spi_mem_programmer) is QSPI
specific and lacks x8 support. This implementation is original and copies no
third-party RTL. These sources do not establish that this design is the smallest
available; physical area must be measured for the intended process or FPGA.
