"""Clock-by-clock tests for the shared score MAC and weighted accumulator.

Score mode (accum_mode = 0): S starts at 0 (subtract = 0) or M (subtract = 1)
and adds or subtracts qi * ki one bit of ki per cycle. The O ring keeps
rotating, bypassing the shared adder. Accumulate mode (accum_mode = 1): the
two-entry O ring adds W * v one bit of v per cycle, and L sums the weights.
"""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


SCORE_MIN = -1040384  # 64 * (-128 * 127)
SCORE_MAX = 1048576   # 64 * (-128 * -128)


def wrap(x, bits):
    return (x + 2**(bits - 1)) % 2**bits - 2**(bits - 1)


@cocotb.test()
async def mac_unit_directed_and_random(dut):
    rng = random.Random(29801)
    for name in ("accum_mode", "load", "subtract", "M", "score_en", "qi", "ki",
                 "first", "accum_en", "W", "sel", "v", "bit_sel"):
        getattr(dut, name).value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    # No register has a reset; None marks a value not yet loaded (X).
    state = {"S": None, "L": None, "ring": [None] * 2, "phase": 0}

    async def cycle(*, accum_mode=1, load=0, subtract=0, maximum=0, score_en=0, qi=0, ki=0,
                    first=0, accum_en=0, weight=0, value=0, bit=0):
        assert not (score_en and accum_mode) and not (accum_en and not accum_mode)
        await FallingEdge(dut.clk)
        dut.accum_mode.value = accum_mode
        dut.load.value = load
        dut.subtract.value = subtract
        dut.M.value = maximum
        dut.score_en.value = score_en
        dut.qi.value = qi
        dut.ki.value = ki
        dut.first.value = first
        dut.accum_en.value = accum_en
        dut.W.value = weight
        dut.sel.value = state["phase"]
        dut.v.value = value
        dut.bit_sel.value = bit

        if load:
            state["S"] = maximum if subtract else 0
        elif score_en and state["S"] is not None:
            product = qi * (-128 if bit == 7 else 1 << bit) if (ki >> bit) & 1 else 0
            state["S"] = wrap(state["S"] - product if subtract else state["S"] + product, 22)
        ring = state["ring"]
        head = ring[0]
        if accum_mode:
            if accum_en and first and bit == 0:
                head = 0
            if head is not None and accum_en and (value >> bit) & 1:
                head = wrap(head + weight * (-128 if bit == 7 else 1 << bit), 20)
        state["ring"] = ring[1:] + [head]
        if accum_en and state["phase"] == 0 and bit == 0:
            state["L"] = weight if first else (None if state["L"] is None else state["L"] + weight)
        state["phase"] ^= 1

        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if state["S"] is not None:
            assert dut.S.value.to_signed() == state["S"], (
                f"S={dut.S.value.to_signed()}, expected={state['S']}")
        for i, want in enumerate(state["ring"]):
            if want is not None:
                got = getattr(dut, f"O{i}").value.to_signed()
                assert got == want, f"O{i}={got}, expected {want}; ring={state['ring']}"
        if state["L"] is not None:
            assert int(dut.L.value) == state["L"], f"L={int(dut.L.value)}, expected {state['L']}"

    async def dot(q, k, *, subtract=0, maximum=0):
        await cycle(accum_mode=0, load=1, subtract=subtract, maximum=maximum)
        for qi, ki in zip(q, k):
            for bit in range(8):
                await cycle(accum_mode=0, subtract=subtract, score_en=1, qi=qi, ki=ki, bit=bit)

    async def idle(n):
        for _ in range(n):
            await cycle(weight=rng.randint(0, 255), bit=rng.randrange(8),
                        value=rng.randint(-128, 127))

    async def token(weight, values, first):
        while state["phase"] != 0:
            await idle(1)
        for bit in range(8):
            for c in range(2):
                await cycle(accum_en=1, first=first, weight=weight, bit=bit, value=values[c])

    # Directed score cases: load wins over en, hold while disabled.
    await cycle(accum_mode=0, load=1, score_en=0, qi=-128, ki=-128, bit=7)
    await cycle(accum_mode=0, score_en=0, qi=127, ki=127, bit=1)  # hold
    for bit in range(8):
        await cycle(accum_mode=0, score_en=1, qi=-128, ki=-128, bit=bit)

    # Full 64-dim scores: pass 1 adds from 0, pass 2 subtracts from M and
    # must give D = M - S. Every intermediate edge is checked.
    cases = [
        ([-128] * 64, [-128] * 64),  # largest score
        ([-128] * 64, [127] * 64),   # smallest score
        ([127] * 64, [127] * 64),
        ([0] * 64, [-128, -1, 1, 127] * 16),
    ]
    cases.extend(([rng.randint(-128, 127) for _ in range(64)],
                  [rng.randint(-128, 127) for _ in range(64)]) for _ in range(60))
    for q, k in cases:
        score = sum(x * y for x, y in zip(q, k))
        await dot(q, k)
        assert state["S"] == score
        maximum = rng.randint(score, SCORE_MAX)
        await dot(q, k, subtract=1, maximum=maximum)
        assert state["S"] == maximum - score
    await dot([-128] * 64, [127] * 64, subtract=1, maximum=SCORE_MAX)
    assert state["S"] == SCORE_MAX - SCORE_MIN  # largest D

    # Weighted sums, with score traffic between tokens as in the controller:
    # the ring must keep its sums while the shared adder serves the score.
    acc_cases = [
        [(255, (-128,) * 2)] * 16,  # minimum signed O
        [(255, (127,) * 2)] * 16,   # maximum positive O
        [(0, (127, -128))] * 16,
        [(255, (-128, 127)), (255, (127, -128))],
        [(255, (-1, 1)), (255, (1, -1))],
    ]
    for _ in range(150):
        acc_cases.append([
            (rng.randint(0, 255), tuple(rng.randint(-128, 127) for _ in range(2)))
            for _ in range(rng.randint(1, 16))
        ])
    for case in acc_cases:
        await idle(rng.randrange(6))  # arbitrary phase and stale sums before token 0
        for i, (weight, values) in enumerate(case):
            if rng.randrange(3) == 0:
                q = [rng.randint(-128, 127) for _ in range(rng.randint(1, 3))]
                await dot(q, [rng.randint(-128, 127) for _ in q], subtract=rng.randrange(2),
                          maximum=rng.randint(SCORE_MIN, SCORE_MAX))
            await token(weight, values, first=i == 0)
            await idle(rng.randrange(3))
        await idle(rng.randrange(9))
        assert state["L"] == sum(weight for weight, _ in case)
        sums = [state["ring"][(c - state["phase"]) % 2] for c in range(2)]
        assert sums == [sum(weight * values[c] for weight, values in case) for c in range(2)]
