"""Clock-by-clock weighted INT4 value accumulation tests."""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


@cocotb.test()
async def accum_directed_and_random(dut):
    rng = random.Random(29803)
    dut.rst_n.value = 0
    dut.clear.value = 0
    dut.en.value = 0
    dut.W.value = 0
    dut.sel.value = 0
    dut.bit_sel.value = 0
    dut.v.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    expected_l = 0
    expected_o = [0] * 4

    async def cycle(*, rst_n=1, clear=0, en=0, weight=0, sel=0, bit=0, value=0):
        nonlocal expected_l, expected_o
        await FallingEdge(dut.clk)
        dut.rst_n.value = rst_n
        dut.clear.value = clear
        dut.en.value = en
        dut.W.value = weight
        dut.sel.value = sel
        dut.bit_sel.value = bit
        dut.v.value = value
        if not rst_n or clear:
            expected_l = 0
            expected_o = [0] * 4
        elif en:
            if sel == 0 and bit == 0:
                expected_l += weight
            if (value >> bit) & 1:  # two's complement bit; bit 3 weighs -8
                expected_o[sel] += weight * (-8 if bit == 3 else 1 << bit)
            expected_o[sel] = (expected_o[sel] + 2**15) % 2**16 - 2**15  # 16-bit wrap
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        got_l = int(dut.L.value)
        got_o = [getattr(dut, f"O{i}").value.to_signed() for i in range(4)]
        assert (got_l, got_o) == (expected_l, expected_o), (
            f"got L={got_l}, O={got_o}; expected L={expected_l}, O={expected_o}; "
            f"rst_n={rst_n}, clear={clear}, en={en}, W={weight}, sel={sel}, bit={bit}, v={value}"
        )

    async def step(weight, values):
        for sel, value in enumerate(values):
            for bit in range(4):
                await cycle(en=1, weight=weight, sel=sel, bit=bit, value=value)

    await cycle(rst_n=0, clear=1, en=1, weight=255, value=-8)
    await step(0, (-8, 7, -1, 1))
    await step(255, (-8, 7, -1, 1))
    await cycle(weight=255, sel=2, value=7)  # hold
    await cycle(clear=1, en=1, weight=255, sel=3, value=7)
    await cycle(rst_n=0, en=1, weight=255, sel=1, value=-8)

    cases = [
        [(255, (-8,) * 4)] * 16,  # minimum signed O
        [(255, (7,) * 4)] * 16,  # maximum positive O
        [(0, (7, -8, 0, 1))] * 16,
        [(255, (-8, 7, -1, 1)), (255, (7, -8, 1, -1))],
    ]
    for _ in range(1000):
        cases.append([
            (rng.randint(0, 255), tuple(rng.randint(-8, 7) for _ in range(4)))
            for _ in range(rng.randint(1, 16))
        ])
    for case in cases:
        await cycle(clear=1, en=1, weight=255, value=7)
        for weight, values in case:
            await step(weight, values)
        await cycle(weight=255, value=-8)
        assert expected_l == sum(weight for weight, _ in case)
        assert expected_o == [sum(weight * values[i] for weight, values in case)
                              for i in range(4)]

    # Keep this stream within the register range by clearing at least every
    # sixteen cycles, while randomizing reset/clear/enable priority.
    for i in range(1000):
        reset = rng.randrange(97) == 0
        clear = i % 16 == 0 or rng.randrange(17) == 0
        await cycle(rst_n=0 if reset else 1, clear=clear,
                    en=rng.choice([0, 1]), weight=rng.randint(0, 255),
                    sel=rng.randrange(4), bit=rng.randrange(4),
                    value=rng.randint(-8, 7))
