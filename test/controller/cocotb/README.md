# Cocotb controller tests

From the repository root, run:

```sh
python3 test/controller/cocotb/run.py
```

The runner uses Icarus Verilog and writes generated files only to a temporary directory. It runs directed and seeded-random INT4 queries against the Python integer model, checks intermediate exponent/divider requests and results, exact memory traffic, and exercises stalls, invalid counts, resets, and consecutive queries. Cocotb models only the external byte memory and host. The controller instantiates the real `exp_lut` and `divider` RTL; the test checks their completion timing and values against the Python reference.

The configured Tiny Tapeout template top can be checked separately with:

```sh
python3 test/controller/cocotb/run_top.py
```
