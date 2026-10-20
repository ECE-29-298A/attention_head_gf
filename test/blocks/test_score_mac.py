import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge

# Use the real Python model as the answer key
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python" / "src"))
from attention_model import dot4


@cocotb.test()
async def test_score_mac(dut):
    random.seed(0)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.qi.value = 0
    dut.ki.value = 0
    dut.clear.value = 0
    dut.en.value = 0

    dut.rst_n.value = 0
    await FallingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1

    cases = [
        ([-8, -8, -8, -8], [-8, -8, -8, -8]),  # biggest possible score
        ([-8, -8, -8, -8], [7, 7, 7, 7]),
    ]
    for _ in range(1000):
        q = [random.randint(-8, 7) for _ in range(4)]
        k = [random.randint(-8, 7) for _ in range(4)]
        cases.append((q, k))

    for q, k in cases:
        # Pulse clear for one tick
        dut.clear.value = 1
        await FallingEdge(dut.clk)
        dut.clear.value = 0

        for (a, b) in zip(q, k):
            dut.qi.value = a
            dut.ki.value = b
            dut.en.value = 1
            await FallingEdge(dut.clk)
            dut.en.value = 0

        got = dut.S.value.to_signed()
        assert got == dot4(q, k), f"q={q} k={k}: S={got}, expected {dot4(q, k)}"
