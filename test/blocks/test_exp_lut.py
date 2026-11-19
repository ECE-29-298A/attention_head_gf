"""Score-pair, rounded-shift and handshake checks for the exponent LUT over the 64-dim INT8 score range."""

import math
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


SCORE_MIN = -1040384  # 64 * (-128 * 127)
SCORE_MAX = 1048576   # 64 * (-128 * -128)


def weight(delta, shift):
    """round(255 · e^(-D'/4)) with D' = round-half-up(D / 2^shift); the table ends at D' = 25."""
    scaled = (delta + ((1 << shift) >> 1)) >> shift
    return round(255 * math.exp(-scaled / 4)) if scaled < 32 else 0


@cocotb.test()
async def exp_lut_exhaustive_and_handshake(dut):
    rng = random.Random(29804)
    dut.rst_n.value = 0
    dut.start.value = 0
    dut.M.value = 0
    dut.S.value = 0
    dut.shift.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    expected_weight = 0

    async def cycle(*, rst_n=1, start=0, maximum=0, score=0, shift=0):
        nonlocal expected_weight
        await FallingEdge(dut.clk)
        dut.rst_n.value = rst_n
        dut.start.value = start
        dut.M.value = maximum
        dut.S.value = score
        dut.shift.value = shift
        if not rst_n:
            expected_weight = 0
            expected_done = 0
        else:
            expected_done = start
            if start:
                expected_weight = weight(max(0, maximum - score), shift)
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        assert int(dut.done.value) == expected_done, (
            f"done={int(dut.done.value)}, expected={expected_done}; "
            f"rst_n={rst_n}, start={start}, M={maximum}, S={score}, shift={shift}"
        )
        assert int(dut.W.value) == expected_weight, (
            f"W={int(dut.W.value)}, expected={expected_weight}; "
            f"rst_n={rst_n}, start={start}, M={maximum}, S={score}, shift={shift}"
        )

    await cycle(rst_n=0, start=1, maximum=SCORE_MAX, score=SCORE_MIN)
    await cycle()
    for delta in range(0, 33):
        await cycle(start=1, maximum=delta, score=0)
    await cycle(start=1, maximum=SCORE_MIN, score=SCORE_MAX)  # contract violation clamps
    await cycle(start=0, maximum=SCORE_MAX, score=SCORE_MIN)  # weight holds
    await cycle(rst_n=0, start=1, maximum=0, score=0)

    # INT8 has ~8.5e9 ordered pairs, too many to sweep. Instead: every D in
    # 0..36 at maxima spread over the range (including both extremes and
    # sign/bit boundaries), with consecutive starts on every cycle.
    maxima = [SCORE_MIN + 36, -32768, -257, -32, -1, 0, 1, 31, 32, 255, 256,
              32767, 32768, SCORE_MAX] + [rng.randint(SCORE_MIN + 36, SCORE_MAX) for _ in range(200)]
    for maximum in maxima:
        for delta in range(37):
            await cycle(start=1, maximum=maximum, score=maximum - delta)
    for delta in (SCORE_MAX - SCORE_MIN, 2**21 - 1, 2**17, 4096, 64, 33, 32, 31, 25, 24):
        await cycle(start=1, maximum=SCORE_MAX, score=SCORE_MAX - delta)
    await cycle(start=0, maximum=0, score=0)

    # Rounded shift: every shift, around every LUT entry boundary (D' = 0..33),
    # exactly at, just below and just above each rounding tie, at both ends of
    # the score range. Includes the largest D with the largest shift.
    for shift in range(16):
        unit, half = 1 << shift, (1 << shift) >> 1
        for scaled in range(34):
            for delta in {scaled * unit + half - 1, scaled * unit + half, scaled * unit + half + 1}:
                if 0 <= delta <= SCORE_MAX - SCORE_MIN:
                    for maximum in (SCORE_MAX, SCORE_MIN + delta):
                        await cycle(start=1, maximum=maximum, score=maximum - delta, shift=shift)
        await cycle(start=1, maximum=SCORE_MAX, score=SCORE_MIN, shift=shift)

    for _ in range(500):
        score = rng.randint(SCORE_MIN, SCORE_MAX)
        maximum = rng.randint(score, SCORE_MAX)
        await cycle(start=1, maximum=maximum, score=score, shift=rng.randrange(16))
        for _ in range(rng.randint(1, 4)):
            await cycle(start=0, maximum=rng.randint(-2**21, 2**21 - 1),
                        score=rng.randint(-2**21, 2**21 - 1), shift=rng.randrange(16))
        if rng.randrange(20) == 0:
            await cycle(rst_n=0, start=1, maximum=maximum, score=score)
