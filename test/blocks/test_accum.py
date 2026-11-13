"""Clock-by-clock tests for the INT8 weighted accumulator (rotating O ring)."""

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


def wrap20(x):
    return (x + 2**19) % 2**20 - 2**19


@cocotb.test()
async def accum_directed_and_random(dut):
    rng = random.Random(29803)
    dut.first.value = 1
    dut.en.value = 0
    dut.W.value = 0
    dut.sel.value = 0
    dut.bit_sel.value = 0
    dut.v.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    # The ring and L have no reset; they are defined once token 0 loads them.
    ring = [None] * 4  # model of [O0, O1, O2, O3]; None = not yet loaded (X)
    L = None
    phase = 0     # caller's free-running phase: O0 holds component `phase`

    def component_sums():
        return [ring[(c - phase) % 4] for c in range(4)]

    async def cycle(*, en=0, first=0, weight=0, bit=0, value=0):
        nonlocal ring, L, phase
        await FallingEdge(dut.clk)
        dut.first.value = first
        dut.en.value = en
        dut.W.value = weight
        dut.sel.value = phase
        dut.bit_sel.value = bit
        dut.v.value = value
        head = 0 if (en and first and bit == 0) else ring[0]
        if head is not None:
            if en and (value >> bit) & 1:  # two's complement bit; bit 7 weighs -128
                head += weight * (-128 if bit == 7 else 1 << bit)
            head = wrap20(head)
        ring = ring[1:] + [head]
        if en and phase == 0 and bit == 0:
            L = weight if first else L + weight
        phase = (phase + 1) % 4
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        for i, want in enumerate(ring):
            if want is not None:
                got = getattr(dut, f"O{i}").value.to_signed()
                assert got == want, f"O{i}={got}, expected {want}; ring={ring}"
        if L is not None:
            assert int(dut.L.value) == L, f"L={int(dut.L.value)}, expected {L}"

    async def idle(n):
        for _ in range(n):
            await cycle(en=0, weight=rng.randint(0, 255), bit=rng.randrange(8),
                        value=rng.randint(-128, 127))

    async def token(weight, values, first):
        while phase != 0:
            await idle(1)
        for bit in range(8):
            for c in range(4):
                await cycle(en=1, first=first, weight=weight, bit=bit, value=values[c])

    cases = [
        [(255, (-128,) * 4)] * 16,  # minimum signed O
        [(255, (127,) * 4)] * 16,  # maximum positive O
        [(0, (127, -128, 0, 1))] * 16,
        [(255, (-128, 127, -1, 1)), (255, (127, -128, 1, -1))],
    ]
    for _ in range(300):
        cases.append([
            (rng.randint(0, 255), tuple(rng.randint(-128, 127) for _ in range(4)))
            for _ in range(rng.randint(1, 16))
        ])
    for case in cases:
        await idle(rng.randrange(6))  # arbitrary phase and stale sums before token 0
        for i, (weight, values) in enumerate(case):
            await token(weight, values, first=i == 0)
            await idle(rng.randrange(3))  # ring keeps turning between tokens
        await idle(rng.randrange(9))
        assert L == sum(weight for weight, _ in case)
        assert component_sums() == [sum(weight * values[i] for weight, values in case)
                                    for i in range(4)]
