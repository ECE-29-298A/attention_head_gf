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
    for name in ("v0", "v1", "v2", "v3"):
        getattr(dut, name).value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    expected_l = 0
    expected_o = [0] * 4

    async def cycle(*, rst_n=1, clear=0, en=0, weight=0, values=(0, 0, 0, 0)):
        nonlocal expected_l, expected_o
        await FallingEdge(dut.clk)
        dut.rst_n.value = rst_n
        dut.clear.value = clear
        dut.en.value = en
        dut.W.value = weight
        for i, value in enumerate(values):
            getattr(dut, f"v{i}").value = value
        if not rst_n or clear:
            expected_l = 0
            expected_o = [0] * 4
        elif en:
            expected_l += weight
            expected_o = [total + weight * value
                          for total, value in zip(expected_o, values)]
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        got_l = int(dut.L.value)
        got_o = [getattr(dut, f"O{i}").value.to_signed() for i in range(4)]
        assert (got_l, got_o) == (expected_l, expected_o), (
            f"got L={got_l}, O={got_o}; expected L={expected_l}, O={expected_o}; "
            f"rst_n={rst_n}, clear={clear}, en={en}, W={weight}, V={values}"
        )

    await cycle(rst_n=0, clear=1, en=1, weight=255, values=(-8,) * 4)
    await cycle(en=1, weight=0, values=(-8, 7, -1, 1))
    await cycle(en=1, weight=255, values=(-8, 7, -1, 1))
    await cycle(weight=255, values=(7,) * 4)  # hold
    await cycle(clear=1, en=1, weight=255, values=(7,) * 4)
    await cycle(rst_n=0, en=1, weight=255, values=(-8,) * 4)

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
        await cycle(clear=1, en=1, weight=255, values=(7,) * 4)
        for weight, values in case:
            await cycle(en=1, weight=weight, values=values)
        await cycle(weight=255, values=(-8,) * 4)
        assert expected_l == sum(weight for weight, _ in case)
        assert expected_o == [sum(weight * values[i] for weight, values in case)
                              for i in range(4)]

    # Keep this stream within the register range by clearing at least every
    # sixteen cycles, while randomizing reset/clear/enable priority.
    for step in range(1000):
        reset = rng.randrange(97) == 0
        clear = step % 16 == 0 or rng.randrange(17) == 0
        await cycle(rst_n=0 if reset else 1, clear=clear,
                    en=rng.choice([0, 1]), weight=rng.randint(0, 255),
                    values=tuple(rng.randint(-8, 7) for _ in range(4)))
