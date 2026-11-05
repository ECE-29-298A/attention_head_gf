"""Clock-by-clock maximum register tests for the INT4 score range."""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


SCORE_MIN = -224
SCORE_MAX = 256


@cocotb.test()
async def max_reg_directed_and_random(dut):
    rng = random.Random(29802)
    dut.rst_n.value = 0
    dut.clear.value = 0
    dut.en.value = 0
    dut.S_in.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    expected = SCORE_MIN

    async def cycle(*, rst_n=1, clear=0, en=0, score=0):
        nonlocal expected
        await FallingEdge(dut.clk)
        dut.rst_n.value = rst_n
        dut.clear.value = clear
        dut.en.value = en
        dut.S_in.value = score
        if not rst_n or clear:
            expected = SCORE_MIN
        elif en:
            expected = max(expected, score)
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        assert dut.M.value.to_signed() == expected, (
            f"M={dut.M.value.to_signed()}, expected={expected}; "
            f"rst_n={rst_n}, clear={clear}, en={en}, score={score}"
        )

    await cycle(rst_n=0, clear=1, en=1, score=SCORE_MAX)
    await cycle(en=1, score=SCORE_MIN)
    await cycle(en=1, score=-100)
    await cycle(en=0, score=SCORE_MAX)  # hold despite larger input
    await cycle(en=1, score=-100)  # equality
    await cycle(en=1, score=SCORE_MAX)
    await cycle(en=1, score=-200)  # cannot decrease
    await cycle(clear=1, en=1, score=SCORE_MAX)  # clear priority
    await cycle(en=1, score=0)
    await cycle(rst_n=0, en=1, score=SCORE_MAX)  # reset during transaction

    for n in range(1, 17):
        for _ in range(50):
            scores = [rng.randint(SCORE_MIN, SCORE_MAX) for _ in range(n)]
            await cycle(clear=1, score=SCORE_MAX)
            for score in scores:
                await cycle(en=1, score=score)
            await cycle(score=SCORE_MAX)
            assert expected == max(scores)

    for _ in range(1000):
        reset = rng.randrange(101) == 0
        clear = rng.randrange(13) == 0
        enable = rng.choice([0, 1])
        await cycle(rst_n=0 if reset else 1, clear=clear, en=enable,
                    score=rng.randint(SCORE_MIN, SCORE_MAX))
