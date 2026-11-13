"""Score-pair and handshake checks for the exponent LUT over the INT8 score range."""

import math
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


SCORE_MIN = -65024
SCORE_MAX = 65536


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

    await cycle(rst_n=0, start=1, maximum=SCORE_MAX, score=SCORE_MIN)
    await cycle()
    for delta in range(0, 17):
        await cycle(start=1, maximum=delta, score=0)
    await cycle(start=1, maximum=SCORE_MIN, score=SCORE_MAX)  # contract violation clamps
    await cycle(start=0, maximum=SCORE_MAX, score=SCORE_MIN)  # weight holds
    await cycle(rst_n=0, start=1, maximum=0, score=0)

    # INT8 has ~8.5e9 ordered pairs, too many to sweep. Instead: every D in
    # 0..20 at maxima spread over the range (including both extremes and
    # sign/bit boundaries), with consecutive starts on every cycle.
    maxima = [SCORE_MIN + 20, -32768, -257, -16, -1, 0, 1, 15, 16, 255, 256,
              32767, 32768, SCORE_MAX] + [rng.randint(SCORE_MIN + 20, SCORE_MAX) for _ in range(200)]
    for maximum in maxima:
        for delta in range(21):
            await cycle(start=1, maximum=maximum, score=maximum - delta)
    for delta in (SCORE_MAX - SCORE_MIN, 2**17 - 1, 2**16, 4096, 32, 31):
        await cycle(start=1, maximum=SCORE_MAX, score=SCORE_MAX - delta)
    await cycle(start=0, maximum=0, score=0)

    for _ in range(500):
        score = rng.randint(SCORE_MIN, SCORE_MAX)
        maximum = rng.randint(score, SCORE_MAX)
        await cycle(start=1, maximum=maximum, score=score)
        for _ in range(rng.randint(1, 4)):
            await cycle(start=0, maximum=rng.randint(-2**17, 2**17 - 1),
                        score=rng.randint(-2**17, 2**17 - 1))
        if rng.randrange(20) == 0:
            await cycle(rst_n=0, start=1, maximum=maximum, score=score)
