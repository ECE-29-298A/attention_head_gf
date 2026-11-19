# Single-tile GF180 INT8 attention

This Tiny Tapeout design calculates one four-component attention output for 1–16
key/value rows. The arithmetic core reads K twice, then V once, and produces
four signed INT8 output bytes. K and V are preloaded in an external QSPI flash;
the current adapter uses the flash's standard `0x03` single-lane read command.

- [Pin protocol and flash layout](docs/info.md)
- [Integration status and verification](docs/integration-report.md)
- [Arithmetic controller](src/attention_controller.sv)
- [QSPI byte engine](docs/spi-byte.md)

Run the full top-level RTL test with `python3 test/top/run.py` or `make -C test`.
The core, arithmetic blocks, and SPI byte engine also have separate regressions.

The current top has not yet been mapped and routed to the GF180 one-tile target.
The reports in `codex-reference/` describe a separate SKY130 design and do not
establish area or timing for this top.
