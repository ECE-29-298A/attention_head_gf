"""Cocotb checks for the currently configured Tiny Tapeout template top."""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Timer


@cocotb.test()
async def directed_and_random_additions(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.ena.value = 1
    dut.rst_n.value = 0
    await Timer(1, unit="ns")
    cases = [(0, 0), (1, 1), (20, 30), (255, 0), (255, 1),
             (128, 128), (255, 255), (0, 255)]
    rng = random.Random(298)
    cases.extend((rng.randrange(256), rng.randrange(256)) for _ in range(300))
    for index, (a, b) in enumerate(cases):
        dut.ui_in.value = a
        dut.uio_in.value = b
        dut.ena.value = index & 1
        dut.rst_n.value = (index >> 1) & 1
        await Timer(1, unit="ns")
        assert int(dut.uo_out.value) == (a + b) & 255, f"{a}+{b}"
        assert int(dut.uio_out.value) == 0
        assert int(dut.uio_oe.value) == 0
