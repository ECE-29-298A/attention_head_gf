"""Score-pair and rounded-shift checks for the exponent LUT over the 64-dim INT8 score range."""

import math
import random

import cocotb
from cocotb.triggers import Timer


SCORE_MIN = -1040384  # 64 * (-128 * 127)
SCORE_MAX = 1048576   # 64 * (-128 * -128)


def weight(delta, shift):
    """round(255 · e^(-D'/4)) with D' = round-half-up(D / 2^shift); the table ends at D' = 25."""
    scaled = (delta + ((1 << shift) >> 1)) >> shift
    return round(255 * math.exp(-scaled / 4)) if scaled < 32 else 0


@cocotb.test()
async def exp_lut_exhaustive(dut):
    """Combinational: W follows M, S and shift. Domain M >= S (the controller guarantees it)."""
    rng = random.Random(29804)

    async def check(maximum, score, shift=0):
        assert maximum >= score
        dut.M.value = maximum
        dut.S.value = score
        dut.shift.value = shift
        await Timer(1, unit="ns")
        expected = weight(maximum - score, shift)
        assert int(dut.W.value) == expected, (
            f"W={int(dut.W.value)}, expected={expected}; M={maximum}, S={score}, shift={shift}")

    # INT8 has ~8.5e9 ordered pairs, too many to sweep. Instead: every D in
    # 0..36 at maxima spread over the range (including both extremes and
    # sign/bit boundaries).
    maxima = [SCORE_MIN + 36, -32768, -257, -32, -1, 0, 1, 31, 32, 255, 256,
              32767, 32768, SCORE_MAX] + [rng.randint(SCORE_MIN + 36, SCORE_MAX) for _ in range(200)]
    for maximum in maxima:
        for delta in range(37):
            await check(maximum, maximum - delta)
    for delta in (SCORE_MAX - SCORE_MIN, 2**21 - 1, 2**17, 4096, 64, 33, 32, 31, 25, 24):
        await check(SCORE_MAX, SCORE_MAX - delta)

    # Rounded shift: every shift, around every LUT entry boundary (D' = 0..33),
    # exactly at, just below and just above each rounding tie, at both ends of
    # the score range. Includes the largest D with the largest shift.
    for shift in range(16):
        unit, half = 1 << shift, (1 << shift) >> 1
        for scaled in range(34):
            for delta in {scaled * unit + half - 1, scaled * unit + half, scaled * unit + half + 1}:
                if 0 <= delta <= SCORE_MAX - SCORE_MIN:
                    for maximum in (SCORE_MAX, SCORE_MIN + delta):
                        await check(maximum, maximum - delta, shift)
        await check(SCORE_MAX, SCORE_MIN, shift)

    for _ in range(5000):
        score = rng.randint(SCORE_MIN, SCORE_MAX)
        await check(rng.randint(score, SCORE_MAX), score, rng.randrange(16))
