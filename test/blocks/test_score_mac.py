"""Clock-by-clock checks for the bit-serial (32-cycle) signed INT8 score MAC."""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


@cocotb.test()
async def score_mac_directed_and_random(dut):
    rng = random.Random(29801)
    dut.rst_n.value = 0
    dut.clear.value = 0
    dut.en.value = 0
    dut.qi.value = 0
    dut.ki.value = 0
    dut.bit_sel.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    expected = 0

    async def cycle(*, rst_n=1, clear=0, en=0, qi=0, ki=0, bit=0):
        nonlocal expected
        await FallingEdge(dut.clk)
        dut.rst_n.value = rst_n
        dut.clear.value = clear
        dut.en.value = en
        dut.qi.value = qi
        dut.ki.value = ki
        dut.bit_sel.value = bit
        if not rst_n or clear:
            expected = 0
        elif en:
            if (ki >> bit) & 1:  # two's complement bit; bit 7 weighs -128
                expected += qi * (-128 if bit == 7 else 1 << bit)
            expected = (expected + 2**17) % 2**18 - 2**17  # 18-bit wrap
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        assert dut.S.value.to_signed() == expected, (
            f"S={dut.S.value.to_signed()}, expected={expected}; "
            f"rst_n={rst_n}, clear={clear}, en={en}, qi={qi}, ki={ki}, bit={bit}"
        )

    async def mac(qi, ki):
        for bit in range(8):
            await cycle(en=1, qi=qi, ki=ki, bit=bit)

    await cycle(rst_n=0, clear=1, en=1, qi=-128, ki=-128, bit=7)
    await mac(-128, -128)
    await mac(-128, -128)
    await cycle(clear=1, en=1, qi=127, ki=127, bit=2)  # clear takes priority
    await cycle(en=0, qi=127, ki=127, bit=1)  # hold
    await mac(-128, 127)
    await cycle(rst_n=0, clear=0, en=1, qi=-128, ki=-128, bit=7)  # reset during sum
    await cycle(en=0, qi=-128, ki=-128, bit=7)

    # End-to-end dot products, including the signed extrema, with each
    # intermediate registered sum checked on every MAC edge.
    cases = [
        ([-128] * 4, [-128] * 4),
        ([-128] * 4, [127] * 4),
        ([127] * 4, [127] * 4),
        ([0] * 4, [-128, -1, 1, 127]),
    ]
    cases.extend(
        ([rng.randint(-128, 127) for _ in range(4)],
         [rng.randint(-128, 127) for _ in range(4)])
        for _ in range(1000)
    )
    for q, k in cases:
        await cycle(clear=1, en=1, qi=q[0], ki=k[0])
        for qi, ki in zip(q, k):
            await mac(qi, ki)
        await cycle(qi=rng.randint(-128, 127), ki=rng.randint(-128, 127))
        assert expected == sum(x * y for x, y in zip(q, k))

    # Mixed control traffic catches accidental accumulation while disabled.
    for _ in range(1000):
        reset = rng.randrange(97) == 0
        clear = rng.randrange(11) == 0
        enable = rng.choice([0, 1])
        await cycle(rst_n=0 if reset else 1, clear=clear, en=enable,
                    qi=rng.randint(-128, 127), ki=rng.randint(-128, 127),
                    bit=rng.randrange(8))
