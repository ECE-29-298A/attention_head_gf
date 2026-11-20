"""Clock-by-clock maximum register tests for the INT8 score range.

Contract: no reset or clear. With en, `first` takes S_in unconditionally,
otherwise M becomes max(M, S_in). Without en, M holds.
"""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


SCORE_MIN = -1040384  # 64 * (-128 * 127)
SCORE_MAX = 1048576   # 64 * (-128 * -128)


@cocotb.test()
async def max_reg_directed_and_random(dut):
    rng = random.Random(29802)
    dut.first.value = 0
    dut.en.value = 0
    dut.S_in.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    expected = None  # undefined until the first `first`

    async def cycle(*, first=0, en=0, score=0):
        nonlocal expected
        await FallingEdge(dut.clk)
        dut.first.value = first
        dut.en.value = en
        dut.S_in.value = score
        if en and (first or (expected is not None and score > expected)):
            expected = score
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if expected is not None:
            assert dut.M.value.to_signed() == expected, (
                f"M={dut.M.value.to_signed()}, expected={expected}; first={first}, en={en}, score={score}")

    await cycle(first=1, en=1, score=SCORE_MIN)
    await cycle(en=1, score=SCORE_MIN)        # equal
    await cycle(en=1, score=SCORE_MIN + 1)    # one larger
    await cycle(first=1, en=0, score=SCORE_MAX)  # first without en: hold
    await cycle(en=0, score=SCORE_MAX)        # hold despite larger input
    await cycle(en=1, score=SCORE_MAX)
    await cycle(en=1, score=SCORE_MAX - 1)    # cannot decrease
    await cycle(first=1, en=1, score=SCORE_MIN)  # first replaces even a larger maximum
    await cycle(en=1, score=-1)
    await cycle(en=1, score=0)                # sign boundary
    await cycle(en=1, score=-2)

    for n in range(1, 17):
        for _ in range(60):
            scores = [rng.randint(SCORE_MIN, SCORE_MAX) for _ in range(n)]
            if rng.randrange(4) == 0:  # many ties and near-ties
                base = rng.randint(SCORE_MIN, SCORE_MAX - 2)
                scores = [base + rng.randrange(3) for _ in range(n)]
            for index, score in enumerate(scores):
                await cycle(first=int(index == 0), en=1, score=score)
                for _ in range(rng.randrange(3)):
                    await cycle(first=rng.randrange(2), en=0, score=rng.randint(SCORE_MIN, SCORE_MAX))
            assert expected == max(scores)

    for _ in range(3000):
        await cycle(first=int(rng.randrange(13) == 0), en=rng.randrange(2),
                    score=rng.randint(SCORE_MIN, SCORE_MAX))
