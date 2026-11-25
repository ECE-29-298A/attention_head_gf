"""End-to-end Tiny Tapeout top test with a bit-accurate 0x03 flash model."""
import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python/src"))
from attention_model import chip_attention, pack_byte, quantize, signed8

SMOLLM = Path(__file__).resolve().parents[2] / "build/smollm_attention.npz"  # python/smollm_extract.py

Q_BASE, K_BASE, V_BASE = 0x000, 0x040, 0x440
MEMORY = V_BASE + 16 * 64


def pad(row):
    """A short Q/K/V row, zero-extended to 64 components."""
    return list(row) + [0] * (64 - len(row))


class Flash:
    def __init__(self):
        self.memory = [0] * MEMORY
        self.prev_cs = 1
        self.prev_sck = 0
        self.bits = 0
        self.command_address = 0
        self.reads = []

    def miso(self):
        if self.prev_cs == 0 and 32 <= self.bits < 40:
            address = self.command_address & 0xFFFFFF
            assert address < len(self.memory), f"flash address {address:#x}"
            return (self.memory[address] >> (39 - self.bits)) & 1
        return 0

    def observe(self, cs, sck, io, oe, abort=False):
        if self.prev_cs and not cs:
            self.bits = 0
            self.command_address = 0
        if not cs and not self.prev_sck and sck:
            if self.bits < 32:
                assert oe & 1, "flash command/address output not driven"
                self.command_address = ((self.command_address << 1) | (io & 1)) & 0xFFFFFFFF
            else:
                assert not (oe & 1), "flash data phase not released"
            self.bits += 1
        if not self.prev_cs and cs:
            if not abort:
                assert self.bits == 40, f"short/long flash transaction: {self.bits} bits"
                assert self.command_address >> 24 == 3, "wrong flash read opcode"
                self.reads.append(self.command_address & 0xFFFFFF)
        self.prev_cs = cs
        self.prev_sck = sck


class Harness:
    def __init__(self, dut):
        self.dut = dut
        self.flash = Flash()
        self.cycles = 0

    async def tick(self, data=0, host=0, reset=1, ena=1):
        d = self.dut
        await FallingEdge(d.clk)
        d.rst_n.value = reset
        d.ena.value = ena
        d.ui_in.value = data
        # IO2/IO3 are pulled high for standard SPI flash WP#/HOLD#.
        d.uio_in.value = 0x0C | (host << 6) | (self.flash.miso() << 1)
        await Timer(1, unit="ns")
        ready = int(d.uio_out.value[7]) if reset and ena else 0
        out = int(d.uo_out.value) if reset and ena else 0
        await RisingEdge(d.clk)
        await Timer(1, unit="ns")
        oe = int(d.uio_oe.value)
        assert (oe & 0xF0) == 0xB0, f"pin directions {oe:#04x}"
        cs = int(d.uio_out.value[5])
        sck = int(d.uio_out.value[4])
        io0 = int(d.uio_out.value[0]) if oe & 1 else 0
        self.flash.observe(cs, sck, io0, oe & 15, abort=not (reset and ena))
        self.cycles += 1
        return ready, out

    async def send(self, value):
        for _ in range(100):
            ready, _ = await self.tick(data=value, host=1)
            if ready:
                return
        assert False, "configuration input did not become ready"

    async def query(self, q, k, v, shift=0, chunk=0, *, name="query"):
        """q: 64 ints; k, v: N rows of 64. Returns V components 4*chunk..4*chunk+3."""
        q, k, v = pad(q), [pad(r) for r in k], [pad(r) for r in v]
        n = len(k)
        self.flash.memory = [0] * MEMORY
        self.flash.memory[Q_BASE:Q_BASE + 64] = [pack_byte(x) for x in q]
        for t in range(n):
            for c in range(64):
                self.flash.memory[K_BASE + 64*t + c] = pack_byte(k[t][c])
                self.flash.memory[V_BASE + 64*t + c] = pack_byte(v[t][c])
        first_read = len(self.flash.reads)
        await self.send(n)
        await self.send(chunk << 4 | shift)

        expected = chip_attention(q, k, [row[4*chunk:4*chunk + 4] for row in v], score_shift=shift)
        received = []
        for index in range(8):  # four 12-bit results, each low byte then sign-extended high byte
            for _ in range(2000000):
                valid, data = await self.tick(host=0)
                if valid:
                    break
            else:
                assert False, f"{name}: timeout before output byte {index}"
            for _ in range(3):
                held_valid, held_data = await self.tick(host=0)
                assert held_valid and held_data == data, "output changed under backpressure"
            valid, transferred = await self.tick(host=1)
            assert valid and transferred == data, "output transfer mismatch"
            received.append(transferred)
        actual = [(signed8(hi) << 8) | lo for lo, hi in zip(received[::2], received[1::2])]

        assert actual == expected, f"{name} (N={n}): hardware={actual}, Python={expected}"
        self.dut._log.info("%s (N=%d, shift=%d, chunk=%d): hardware=%s, Python=%s",
                           name, n, shift, chunk, actual, expected)

        # Per token: 64 dimensions of one Q byte then one K byte; pass 2 adds the V chunk.
        def score_reads(t):
            return [base + d for d in range(64) for base in (Q_BASE, K_BASE + 64*t)]
        expected_reads = [a for t in range(n) for a in score_reads(t)]
        for t in range(n):
            expected_reads += score_reads(t) + [V_BASE + 64*t + 4*chunk + c for c in range(4)]
        assert self.flash.reads[first_read:] == expected_reads, "Q/K/V read order or count"


async def start_harness(dut):
    dut.rst_n.value = 0
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0x0C
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    h = Harness(dut)
    await h.tick(reset=0)
    await h.tick(reset=0)
    return h


@cocotb.test()
async def end_to_end_flash_and_host(dut):
    h = await start_harness(dut)
    for invalid in (0, 17, 255):
        ready, _ = await h.tick(data=invalid, host=1)
        assert not ready, "invalid token count accepted"

    await h.query([1, 0, 0, 0], [[-128, 0, 0, 0]], [[-128, -1, 0, 127]])
    await h.query([1, 0, 0, 0], [[0, 0, 0, 0], [1, 0, 0, 0]],
                  [[-128, 0, 127, 1], [127, 1, -128, -1]])
    rng = random.Random(298)
    q = [1, 0, 0, 0]
    k = [[t-8, 0, 0, 0] for t in range(16)]  # maximum at last token
    v = [[rng.randint(-128, 127) for _ in range(64)] for _ in range(16)]
    await h.query(q, k, v, shift=1, chunk=15)

    # Abort after a flash transaction begins, then start a fresh query.
    await h.send(1)
    await h.send(0)
    for _ in range(100):
        await h.tick()
        if not h.flash.prev_cs and h.flash.bits >= 12:
            break
    else:
        assert False, "QSPI transfer never started"
    await h.tick(reset=0)
    await h.tick(reset=0)
    assert h.flash.prev_cs == 1, "reset did not release flash CS"
    await h.query([0, 0, 0, 0], [[0, 0, 0, 0]], [[127, -128, 1, -1]])
    await h.send(1)
    await h.send(0)
    for _ in range(100):
        await h.tick()
        if not h.flash.prev_cs and h.flash.bits >= 12:
            break
    else:
        assert False, "QSPI transfer never started before ena abort"
    await h.tick(ena=0)
    await h.tick(ena=0)
    assert h.flash.prev_cs == 1, "ena low did not release flash CS"
    await h.query([0, 0, 0, 0], [[0, 0, 0, 0]], [[-1, 0, 1, 127]])
    dut._log.info("PASS top: flash reads, 12-bit outputs, backpressure, boundaries, reset/ena abort; %d cycles", h.cycles)


@cocotb.test()
async def hardware_matches_python_model(dut):
    h = await start_harness(dut)
    await h.query(
        [127, -128, 37, -9],
        [[-128, 127, 11, 3]],
        [[-128, 127, -1, 0]],
        name="single token with signed extremes",
    )
    await h.query(
        [0, 0, 0, 0],
        [[1, -2, 3, -4], [-5, 6, -7, 8]],
        [[0, 0, 127, -128], [1, -1, 126, -127]],
        name="equal scores with positive and negative rounding ties",
    )
    # Score deltas are 24, 1, 25, 0. The first two outputs distinguish
    # dropping the weight at delta 24 from retaining one at delta 25.
    await h.query(
        [1, 0, 0, 0],
        [[-25, 0, 0, 0], [-2, 0, 0, 0], [-26, 0, 0, 0], [-1, 0, 0, 0]],
        [[-128, 0, -128, 127], [0, 0, 127, -128], [0, -128, 127, -128], [1, 1, -128, 127]],
        name="negative scores at the LUT cutoff",
    )
    # Largest 64-dim score gap (2088960): only shift 15 brings it near the table.
    await h.query(
        [-128] * 64,
        [[127] * 64, [-128] * 64],
        [[127, -128, 7, -11], [-1, 3, -9, 42]],
        shift=15,
        name="largest representable INT8 dot product gap",
    )
    # Shift 3: D = 19, 20, 21 round to 2, 3 (tie, half up), 3; truncating gives 2, 2, 2.
    await h.query(
        [1],
        [[0], [-19], [-20], [-21]],
        [[1, 2, 3, 4], [-128, 127, 0, 0], [0, 0, -128, 127], [64, -64, 32, -32]],
        shift=3,
        name="rounded score shift ties",
    )
    rng = random.Random(2026)
    await h.query(
        [rng.randint(-40, 40) for _ in range(64)],
        [[rng.randint(-40, 40) for _ in range(64)] for _ in range(8)],
        [[rng.randint(-128, 127) for _ in range(64)] for _ in range(8)],
        shift=8, chunk=11,
        name="seeded 64-dim mixed weights",
    )
    await h.query(
        [-128] * 64,
        [[-128] * 64] * 16,
        [[-128, 127, -1, 1] * 16] * 16,
        shift=15, chunk=15,
        name="sixteen maximum weights with extreme values",
    )


@cocotb.test(skip=not SMOLLM.exists())
async def real_smollm_head(dut):
    """One real SmolLM-135M head (layer 14, head 4, last of 16 tokens) through the pins."""
    import numpy as np
    data = np.load(SMOLLM)
    prompt, layer, head, chunk = 0, 14, 4, 5
    q = data["q"][prompt, layer, head, -1].astype(np.float64)
    k, v = (data[n][prompt, layer, head // 3].astype(np.float64) for n in ("k", "v"))
    ref = data["out"][prompt, layer, head, -1]
    # Host side: power-of-two INT8, per-channel V; shift makes one LUT unit 0.25 nat.
    qi, eq = quantize(q, axis=-1)
    ki, ek = quantize(k, axis=(-2, -1))
    vi, ev = quantize(v, axis=-2)
    shift = int(eq[0] + ek[0, 0] + 1)  # q·k · 2^-(eq+ek) / 8 nats, 4 units per nat
    h = await start_harness(dut)
    await h.query(qi.tolist(), ki.tolist(), vi.tolist(), shift, chunk, name="real SmolLM head")
    got = chip_attention(qi.tolist(), ki.tolist(), [r[4*chunk:4*chunk + 4] for r in vi.tolist()],
                         score_shift=shift)  # = the RTL, asserted inside query()
    est = np.array(got) / 16 * 2.0 ** -ev[0, 4*chunk:4*chunk + 4]
    dut._log.info("SmolLM float output %s, chip %s", np.round(ref[4*chunk:4*chunk + 4], 4), np.round(est, 4))
