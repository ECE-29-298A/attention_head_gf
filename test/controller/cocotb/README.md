# Cocotb controller tests

From the repository root, run:

```sh
python3 test/controller/cocotb/run.py
```

The runner uses Icarus Verilog and writes generated files only to a temporary directory. It runs directed and seeded-random INT4 queries against the Python integer model, checks intermediate exponent/divider requests and exact memory traffic, and exercises stalls, invalid counts, resets, and consecutive queries. The memory responder and divider are behavioral Cocotb models; there is no divider RTL in this repository. The exponent is modeled using the Python reference; `src/exp_lut.v` has its own block-level Cocotb tests.

The configured Tiny Tapeout template top can be checked separately with:

```sh
python3 test/controller/cocotb/run_top.py
```
