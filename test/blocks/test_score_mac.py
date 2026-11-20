"""Clock-by-clock checks for the bit-serial signed INT8 score MAC (64-dim, 22-bit).

Contract: no reset or clear. `first` (only together with en) starts a new sum
from 0; with en low S must hold whatever qi, ki and bit_sel do. S_next is the
value S takes on the next edge and must be valid combinationally.
"""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


def wrap22(x):
    return (x + 2**21) % 2**22 - 2**21


@cocotb.test()
async def score_mac_directed_and_random(dut):
    rng = random.Random(29801)
    dut.first.value = 0
    dut.en.value = 0
    dut.qi.value = 0
    dut.ki.value = 0
    dut.bit_sel.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    expected = None  # S is undefined until the first `first`

    async def cycle(*, first=0, en=0, qi=0, ki=0, bit=0):
        nonlocal expected
        assert en or not first, "testbench: first is only legal with en"
        await FallingEdge(dut.clk)
        dut.first.value = first
        dut.en.value = en
        dut.qi.value = qi
        dut.ki.value = ki
        dut.bit_sel.value = bit
        if en:
            base = 0 if first else expected
            if base is not None:
                term = qi * (-128 if bit == 7 else 1 << bit) if (ki >> bit) & 1 else 0
                expected = wrap22(base + term)
        await Timer(1, unit="ns")
        if expected is not None:
            assert dut.S_next.value.to_signed() == expected, (
                f"S_next={dut.S_next.value.to_signed()}, expected={expected}; "
                f"first={first}, en={en}, qi={qi}, ki={ki}, bit={bit}")
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if expected is not None:
            assert dut.S.value.to_signed() == expected, (
                f"S={dut.S.value.to_signed()}, expected={expected}; "
                f"first={first}, en={en}, qi={qi}, ki={ki}, bit={bit}")

    async def mac(qi, ki, first=False):
        for bit in range(8):
            await cycle(first=int(first and bit == 0), en=1, qi=qi, ki=ki, bit=bit)

    async def idle(n):
        # Disabled cycles with live-looking operands must not move S.
        for _ in range(n):
            await cycle(qi=rng.randint(-128, 127), ki=rng.randint(-128, 127), bit=rng.randrange(8))

    await mac(-128, -128, first=True)
    await idle(5)
    await mac(-128, -128)
    await mac(-128, 127, first=True)  # first restarts a sum mid-way

    # End-to-end dot products, including the signed extrema and the 22-bit
    # bounds, with every intermediate sum checked, and idle gaps between components.
    cases = [
        ([-128] * 64, [-128] * 64),  # largest score, 1048576
        ([-128] * 64, [127] * 64),   # smallest score, -1040384
        ([127] * 64, [127] * 64),
        ([127] * 64, [-128] * 64),
        ([0] * 64, [-128, -1, 1, 127] * 16),
        ([-1] * 64, [-1] * 64),
    ]
    cases.extend(
        ([rng.randint(-128, 127) for _ in range(64)], [rng.randint(-128, 127) for _ in range(64)])
        for _ in range(300))
    for q, k in cases:
        for index, (qi, ki) in enumerate(zip(q, k)):
            await mac(qi, ki, first=index == 0)
            if rng.randrange(4) == 0:
                await idle(rng.randint(1, 3))
        assert expected == sum(x * y for x, y in zip(q, k))
        await idle(rng.randint(0, 3))

    # Random legal traffic: any bit order, random first, long holds.
    for _ in range(3000):
        en = rng.randrange(3) != 0
        await cycle(first=int(en and rng.randrange(10) == 0), en=int(en),
                    qi=rng.randint(-128, 127), ki=rng.randint(-128, 127), bit=rng.randrange(8))
