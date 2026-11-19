# Verification

The configured Tiny Tapeout top is `tt_um_attention_head_gf`. The default
`make` in this directory tests full attention transactions through a pin-level
QSPI flash model. It checks the host ready/valid protocol, flash command and
address bits, K/K/V read order, output values and stalls, invalid token counts,
reset, `ena` abort, and consecutive queries.

From the repository root:

```sh
make -C test
python3 -m cocotb_tools.check_results test/results.xml
python3 test/top/run.py
```

The standalone top runner builds in a temporary directory. The Makefile run
also supports the `GATES=yes` gate-level flow once a netlist is produced.

Other regressions:

```sh
python3 test/controller/run.py
python3 test/controller/cocotb/run.py
python3 test/divider/run.py
make -C test/spi_byte test lint
```

Block-level Cocotb tests are in `test/blocks`. See the
[integration report](../docs/integration-report.md) for scope and remaining
physical verification.
