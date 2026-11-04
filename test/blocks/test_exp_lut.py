import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge

# Use the Python model as the answer key
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python" / "src"))
from attention_model import exp_weight  # noqa: E402

# Every score q·k can reach with INT4: 4 · (-8 · 7) = -224 up to 4 · (-8 · -8) = 256
S_MIN, S_MAX = -224, 256


async def reset(dut):
    dut.start.value = 0
    dut.M.value = 0
    dut.S.value = 0
    dut.rst_n.value = 0
    await FallingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    await FallingEdge(dut.clk)


@cocotb.test()
async def test_exp_lut_exhaustive(dut):
    """Every valid (M, S) pair with M >= S, back to back, one start per cycle."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)

    # Inputs go in before a rising edge; by the next falling edge the
    # result for THIS pair is already registered.
    checked = 0
    for M in range(S_MIN, S_MAX + 1):
        for S in range(S_MIN, M + 1):
            dut.M.value = M
            dut.S.value = S
            dut.start.value = 1
            await FallingEdge(dut.clk)

            assert dut.done.value == 1, f"done missing for M={M}, S={S}"
            got = int(dut.W.value)
            want = exp_weight(M, S)
            assert got == want, f"M={M}, S={S}, D={M - S}: W={got}, expected {want}"
            checked += 1

    dut.start.value = 0
    await FallingEdge(dut.clk)
    assert dut.done.value == 0

    assert checked == sum(range(1, S_MAX - S_MIN + 2)), "missed some pairs"
    dut._log.info(f"checked {checked} (M, S) pairs")


@cocotb.test()
async def test_exp_lut_handshake(dut):
    """done is a one-cycle pulse a cycle after start; W holds until the next start."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)
    random.seed(298)

    assert dut.done.value == 0, "done high after reset"
    assert int(dut.W.value) == 0, "W not cleared by reset"

    for _ in range(500):
        S = random.randint(S_MIN, S_MAX)
        M = random.randint(S, S_MAX)

        dut.M.value = M
        dut.S.value = S
        dut.start.value = 1
        await FallingEdge(dut.clk)
        dut.start.value = 0
        # Junk on the inputs must not matter once start is gone
        dut.M.value = random.randint(-512, 511)
        dut.S.value = random.randint(-512, 511)

        assert dut.done.value == 1, "done should pulse the cycle after start"
        want = exp_weight(M, S)
        assert int(dut.W.value) == want

        # Idle for a few cycles: done drops, W stays
        for _ in range(random.randint(1, 4)):
            await FallingEdge(dut.clk)
            assert dut.done.value == 0, "done stayed high"
            assert int(dut.W.value) == want, "W changed without a start"

    # Reset in the middle clears everything
    dut.M.value = 0
    dut.S.value = 0
    dut.start.value = 1
    await FallingEdge(dut.clk)
    dut.start.value = 0
    await reset(dut)
    assert dut.done.value == 0 and int(dut.W.value) == 0, "reset did not clear"


@cocotb.test()
async def test_exp_lut_bad_order(dut):
    """M < S breaks the contract. The LUT clamps D to 0, so W = 255 instead of garbage."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset(dut)

    for M, S in [(0, 1), (-224, 256), (100, 101), (-1, 0)]:
        dut.M.value = M
        dut.S.value = S
        dut.start.value = 1
        await FallingEdge(dut.clk)
        assert dut.done.value == 1
        assert int(dut.W.value) == 255, f"M={M}, S={S}: W={int(dut.W.value)}, expected clamp to 255"
    dut.start.value = 0
