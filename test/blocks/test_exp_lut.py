"""Exhaustive score-pair and handshake checks for the exponent LUT."""

import math
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


SCORE_MIN = -224
SCORE_MAX = 256


@cocotb.test()
async def exp_lut_exhaustive_and_handshake(dut):
    rng = random.Random(29804)
    dut.rst_n.value = 0
    dut.start.value = 0
    dut.M.value = 0
    dut.S.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    expected_weight = 0

    async def cycle(*, rst_n=1, start=0, maximum=0, score=0):
        nonlocal expected_weight
        await FallingEdge(dut.clk)
        dut.rst_n.value = rst_n
        dut.start.value = start
        dut.M.value = maximum
        dut.S.value = score
        if not rst_n:
            expected_weight = 0
            expected_done = 0
        else:
            expected_done = start
            if start:
                delta = max(0, maximum - score)
                expected_weight = round(255 * math.exp(-delta / 2)) if delta < 16 else 0
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        assert int(dut.done.value) == expected_done, (
            f"done={int(dut.done.value)}, expected={expected_done}; "
            f"rst_n={rst_n}, start={start}, M={maximum}, S={score}"
        )
        assert int(dut.W.value) == expected_weight, (
            f"W={int(dut.W.value)}, expected={expected_weight}; "
            f"rst_n={rst_n}, start={start}, M={maximum}, S={score}"
        )

    await cycle(rst_n=0, start=1, maximum=256, score=-224)
    await cycle()
    for delta in range(0, 17):
        await cycle(start=1, maximum=delta, score=0)
    await cycle(start=1, maximum=-224, score=256)  # contract violation clamps
    await cycle(start=0, maximum=256, score=-224)  # weight holds
    await cycle(rst_n=0, start=1, maximum=0, score=0)

    # Every reachable ordered pair, with consecutive starts on every cycle.
    # This exercises both positive and negative signed input encodings.
    checked = 0
    for maximum in range(SCORE_MIN, SCORE_MAX + 1):
        for score in range(SCORE_MIN, maximum + 1):
            await cycle(start=1, maximum=maximum, score=score)
            checked += 1
    assert checked == 115921
    await cycle(start=0, maximum=0, score=0)

    for _ in range(500):
        score = rng.randint(SCORE_MIN, SCORE_MAX)
        maximum = rng.randint(score, SCORE_MAX)
        await cycle(start=1, maximum=maximum, score=score)
        for _ in range(rng.randint(1, 4)):
            await cycle(start=0, maximum=rng.randint(-512, 511),
                        score=rng.randint(-512, 511))
        if rng.randrange(20) == 0:
            await cycle(rst_n=0, start=1, maximum=maximum, score=score)
