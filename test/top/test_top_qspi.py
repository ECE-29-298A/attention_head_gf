"""End-to-end Tiny Tapeout top test with a bit-accurate 0x03 sequential-read flash model."""
import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python/src"))
from attention_model import chip_attention, quantize, signed8, tape

SMOLLM = Path(__file__).resolve().parents[2] / "build/smollm_attention.npz"  # python/smollm_extract.py

def pad(row):
    """A short Q/K/V row, zero-extended to 64 components."""
    return list(row) + [0] * (64 - len(row))


class Flash:
    """Standard 0x03 read: one command and address, then bytes in order until CS rises."""

    def __init__(self):
        self.memory = [0]
        self.prev_cs = 1
        self.prev_sck = 0
        self.bits = 0
        self.command_address = 0

    def miso(self):
        index = self.bits - 32
        if self.prev_cs == 0 and 0 <= index < 8 * len(self.memory):
            address = (self.command_address & 0xFFFFFF) + index // 8
            return (self.memory[address] >> (7 - index % 8)) & 1
        return 0

    def observe(self, cs, sck, mosi):
        if self.prev_cs and not cs:
            self.bits = 0
            self.command_address = 0
        if not cs and not self.prev_sck and sck:
            if self.bits < 32:
                self.command_address = (self.command_address << 1) | mosi
            self.bits += 1
            if self.bits == 32:
                assert self.command_address == 0x03000000, f"flash command {self.command_address:#010x}"
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
        assert int(d.uio_oe.value) == 0xB1, f"pin directions {int(d.uio_oe.value):#04x}"
        cs = int(d.uio_out.value[5])
        # MOSI only matters while the flash is selected.
        self.flash.observe(cs, int(d.uio_out.value[4]), 0 if cs else int(d.uio_out.value[0]))
        self.cycles += 1
        return ready, out

    async def send(self, value):
        for _ in range(100):
            ready, _ = await self.tick(data=value, host=1)
            if ready:
                return
        assert False, "configuration input did not become ready"

    async def run(self, n, shift, cont, expected, name):
        """One run: count byte N, config byte {cont, 000, shift}, then four result bytes."""
        await self.send(n)
        await self.send(cont << 7 | shift)
        received = []
        for index in range(4):  # two 12-bit results, each low byte then sign-extended high byte
            for _ in range(200000):
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

    async def head(self, q, k, v, shift=0, chunks=(0,), *, name="query"):
        """q: 64 ints; k, v: N rows of 64. Runs the chunks in order: one fresh run, then cont runs."""
        q, k, v = pad(q), [pad(r) for r in k], [pad(r) for r in v]
        self.flash.memory = tape(q, k, v, chunks)
        start = self.cycles
        for i, chunk in enumerate(chunks):
            expected = chip_attention(q, k, [row[2*chunk:2*chunk + 2] for row in v], score_shift=shift)
            await self.run(len(k), shift, int(i > 0), expected, f"{name} chunk {chunk}")
            # The chip clocks exactly the bits of the tape so far, and never restarts mid-head.
            consumed = 128 * len(k) * (2 + i) + 2 * len(k) * (1 + i)
            assert self.flash.bits == 32 + 8 * consumed, f"{name}: {self.flash.bits - 32} tape bits read"
        assert consumed == len(self.flash.memory)
        self.dut._log.info("%s (N=%d, shift=%d, chunks=%s): matches Python, %d cycles",
                           name, len(k), shift, list(chunks), self.cycles - start)

    async def query(self, q, k, v, shift=0, chunk=0, *, name="query"):
        await self.head(q, k, v, shift, (chunk,), name=name)


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
    # Count byte N: outside 1..16 is refused.
    for invalid in (0, 17, 255, 0x20, 0x31, 0x41, 0x81):
        ready, _ = await h.tick(data=invalid, host=1)
        assert not ready, "invalid token count accepted"

    await h.query([1, 0, 0, 0], [[-128, 0, 0, 0]], [[-128, -1, 0, 127]])
    await h.query([1, 0, 0, 0], [[-128, 0, 0, 0]], [[-128, -1, 0, 127]], chunk=1)
    await h.query([1, 0, 0, 0], [[0, 0, 0, 0], [1, 0, 0, 0]],
                  [[-128, 0, 127, 1], [127, 1, -128, -1]])
    rng = random.Random(298)
    q = [1, 0, 0, 0]
    k = [[t-8, 0, 0, 0] for t in range(16)]  # maximum at last token
    v = [[rng.randint(-128, 127) for _ in range(64)] for _ in range(16)]
    await h.query(q, k, v, shift=1, chunk=31)

    # Abort after a flash transaction begins, then start a fresh query.
    await h.send(1)
    await h.send(0)
    for _ in range(100):
        await h.tick()
        if not h.flash.prev_cs and h.flash.bits >= 12:
            break
    else:
        assert False, "flash read never started"
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
        assert False, "flash read never started before ena abort"
    await h.tick(ena=0)
    await h.tick(ena=0)
    assert h.flash.prev_cs == 1, "ena low did not release flash CS"
    await h.query([0, 0, 0, 0], [[0, 0, 0, 0]], [[-1, 0, 1, 127]])
    dut._log.info("PASS top: tape reads, 12-bit outputs, backpressure, boundaries, reset/ena abort; %d cycles", h.cycles)


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
        shift=8, chunk=27,
        name="seeded 64-dim mixed weights",
    )
    await h.query(
        [-128] * 64,
        [[-128] * 64] * 16,
        [[-128, 127, -1, 1] * 16] * 16,
        shift=15, chunk=30,
        name="sixteen maximum weights with extreme values",
    )


@cocotb.test()
async def continue_runs_share_pass_one(dut):
    """Several chunks of one head: a fresh run, then cont runs that reuse the maximum and the open read."""
    h = await start_harness(dut)
    rng = random.Random(64)
    vec = lambda lo=-128, hi=127: [rng.randint(lo, hi) for _ in range(64)]
    for n, shift in ((16, 13), (5, 9), (1, 0)):
        await h.head(vec(-40, 40) if n == 5 else vec(), [vec() for _ in range(n)], [vec() for _ in range(n)],
                     shift, (0, 31, 17, 5), name="four chunks")
    # A fresh run after cont runs restarts the read; a reset mid-head releases the flash.
    await h.head(vec(), [vec() for _ in range(3)], [vec() for _ in range(3)], 12, (9, 10), name="restart")
    await h.send(3)
    await h.send(0x80 | 12)
    for _ in range(50):
        await h.tick()
    assert h.flash.prev_cs == 0, "cont run dropped the flash read"
    await h.tick(reset=0)
    await h.tick(reset=0)
    assert h.flash.prev_cs == 1, "reset did not release flash CS"
    await h.query(vec(), [vec() for _ in range(2)], [vec() for _ in range(2)], 14, 3, name="after abort")


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
    got = chip_attention(qi.tolist(), ki.tolist(), [r[2*chunk:2*chunk + 2] for r in vi.tolist()],
                         score_shift=shift)  # = the RTL, asserted inside query()
    est = np.array(got) / 16 * 2.0 ** -ev[0, 2*chunk:2*chunk + 2]
    dut._log.info("SmolLM float output %s, chip %s", np.round(ref[2*chunk:2*chunk + 2], 4), np.round(est, 4))
