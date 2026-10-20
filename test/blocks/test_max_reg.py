import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge

@cocotb.test()
async def test_max_reg(dut):
    random.seed(0)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.S_in.value = 0
    dut.clear.value = 0
    dut.en.value = 0

    dut.rst_n.value = 0
    await FallingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1

    cases = [
        [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
        [23, 24, 25],
        [-224],
        [-224, -224, -224],
        [-5, -100, -3],
        [10, 20, 30, 256],
        
    ]
    for _ in range(1000):
        n = random.randint(1, 16)
        cases.append([random.randint(-224, 256) for _ in range(n)])

    for scores in cases:
        # Pulse clear for one tick
        dut.clear.value = 1
        await FallingEdge(dut.clk)
        dut.clear.value = 0

        # Put each one in S_in and pulse en.
        for num in scores:

            dut.S_in.value = num

            # Pulsing en
            dut.en.value = 1
            await FallingEdge(dut.clk)
            dut.en.value = 0
            dut.S_in.value = random.randint(-512, 511)   # junk, should be ignored
            await FallingEdge(dut.clk)

        got = dut.M.value.to_signed()
        assert got == max(scores), f"case = {list}: M={got}, expected {max(scores)}"
