# Project tests

## Attention arithmetic

Run from the repository root with Python + NumPy and Verilator:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 test/controller/run.py
PYTHONDONTWRITEBYTECODE=1 python3 test/divider/run.py
```

The controller regression uses all five real arithmetic modules and models only
host/memory behavior. It checks 138 Python-model queries under seven memory/stall
configurations, intermediate values, reset and handshake behavior. The former
separate core test and mock-arithmetic controller test are consolidated here.
The divider regression adds 108,641 arithmetic/boundary/invalid-input cases.
Both runners build in temporary directories and leave no generated repo files.

The four Cocotb block tests in `test/blocks` remain for additional exhaustive
and control-contract checks. See [block testing](../docs/blocks.md#verification)
and [controller coverage](../docs/controller.md#verification).

## Tiny Tapeout template testbench

The default `test/Makefile` still builds `src/project.v`, the template adder,
not the attention controller. Keep this test until the chip top-level is wired
up; it tests the current physical-build entry point, not duplicate attention
arithmetic. The remaining instructions apply to that template testbench.

This is a sample testbench for a Tiny Tapeout project. It uses [cocotb](https://docs.cocotb.org/en/stable/) to drive the DUT and check the outputs.
See below to get started or for more information, check the [website](https://tinytapeout.com/hdl/testing/).

## Setting up

1. Edit [Makefile](Makefile) and modify `PROJECT_SOURCES` to point to your Verilog files.
2. Edit [tb.v](tb.v) and replace `tt_um_example` with your module name.

## How to run

To run the RTL simulation:

```sh
make -B
```

To run gatelevel simulation, first harden your project and copy `../runs/wokwi/results/final/verilog/gl/{your_module_name}.v` to `gate_level_netlist.v`.

Then run:

```sh
make -B GATES=yes
```

If you wish to save the waveform in VCD format instead of FST format, edit tb.v to use `$dumpfile("tb.vcd");` and then run:

```sh
make -B FST=
```

This will generate `tb.vcd` instead of `tb.fst`.

## How to view the waveform file

Using GTKWave

```sh
gtkwave tb.fst tb.gtkw
```

Using Surfer

```sh
surfer tb.fst
```
