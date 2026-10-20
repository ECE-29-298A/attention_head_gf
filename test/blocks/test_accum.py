import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge

@cocotb.test()
async def test_accum(dut):
    random.seed(0)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.clear.value = 0
    dut.en.value = 0
    dut.W.value = 0
    dut.v0.value = 0
    dut.v1.value = 0
    dut.v2.value = 0
    dut.v3.value = 0

    dut.rst_n.value = 0
    await FallingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1

    cases = [
        [(255, [-8, -8, -8, -8])] * 16,     # most negative O
        [(255, [7, 7, 7, 7])] * 16,         # most positive O
        [(0, [3, -2, 5, 1])],               # zero weight, everything should stay 0
    ]

    for _ in range(1000):
        n = random.randint(1, 16)
        case = []
        for _ in range(n):
            W = random.randint(0, 255)
            v = [random.randint(-8, 7) for _ in range(4)]
            case.append((W, v))
        cases.append(case)

    for case in cases:
        # Pulse clear for one tick
        dut.clear.value = 1
        await FallingEdge(dut.clk)
        dut.clear.value = 0

        for W, v in case:

            dut.W.value = W
            dut.v0.value = v[0]
            dut.v1.value = v[1]
            dut.v2.value = v[2]
            dut.v3.value = v[3]

            # Pulsing en
            dut.en.value = 1
            await FallingEdge(dut.clk)
            dut.en.value = 0

        
        got_L = dut.L.value.to_unsigned()
        got_O = [dut.O0.value.to_signed(), dut.O1.value.to_signed(),
         dut.O2.value.to_signed(), dut.O3.value.to_signed()]
        expected_L = sum(W for W, v in case)
        expected_O = [sum(W * v[i] for W, v in case) for i in range(4)]

        assert got_L == expected_L, f"case = {case}: L={got_L}, expected {expected_L}"
        assert got_O == expected_O, f"case={case}: O={got_O}, expected {expected_O}"