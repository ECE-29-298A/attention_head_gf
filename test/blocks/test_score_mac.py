"""Clock-by-clock checks for the bit-serial (16-cycle) signed INT4 score MAC."""

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
            if (ki >> bit) & 1:  # two's complement bit; bit 3 weighs -8
                expected += qi * (-8 if bit == 3 else 1 << bit)
            expected = (expected + 512) % 1024 - 512  # 10-bit wrap
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        assert dut.S.value.to_signed() == expected, (
            f"S={dut.S.value.to_signed()}, expected={expected}; "
            f"rst_n={rst_n}, clear={clear}, en={en}, qi={qi}, ki={ki}, bit={bit}"
        )

    async def mac(qi, ki):
        for bit in range(4):
            await cycle(en=1, qi=qi, ki=ki, bit=bit)

    await cycle(rst_n=0, clear=1, en=1, qi=-8, ki=-8, bit=3)
    await mac(-8, -8)
    await mac(-8, -8)
    await cycle(clear=1, en=1, qi=7, ki=7, bit=2)  # clear takes priority
    await cycle(en=0, qi=7, ki=7, bit=1)  # hold
    await mac(-8, 7)
    await cycle(rst_n=0, clear=0, en=1, qi=-8, ki=-8, bit=3)  # reset during sum
    await cycle(en=0, qi=-8, ki=-8, bit=3)

    # End-to-end dot products, including the signed extrema, with each
    # intermediate registered sum checked on every MAC edge.
    cases = [
        ([-8] * 4, [-8] * 4),
        ([-8] * 4, [7] * 4),
        ([7] * 4, [7] * 4),
        ([0] * 4, [-8, -1, 1, 7]),
    ]
    cases.extend(
        ([rng.randint(-8, 7) for _ in range(4)],
         [rng.randint(-8, 7) for _ in range(4)])
        for _ in range(1000)
    )
    for q, k in cases:
        await cycle(clear=1, en=1, qi=q[0], ki=k[0])
        for qi, ki in zip(q, k):
            await mac(qi, ki)
        await cycle(qi=rng.randint(-8, 7), ki=rng.randint(-8, 7))
        assert expected == sum(x * y for x, y in zip(q, k))

    # Mixed control traffic catches accidental accumulation while disabled.
    for _ in range(1000):
        reset = rng.randrange(97) == 0
        clear = rng.randrange(11) == 0
        enable = rng.choice([0, 1])
        await cycle(rst_n=0 if reset else 1, clear=clear, en=enable,
                    qi=rng.randint(-8, 7), ki=rng.randint(-8, 7),
                    bit=rng.randrange(4))
