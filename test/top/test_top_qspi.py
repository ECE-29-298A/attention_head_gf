"""End-to-end Tiny Tapeout top test: an asynchronous SPI host and a bit-accurate 0x6B quad-output flash model."""
import os
import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python/src"))
from attention_model import chip_attention, config_frame, decode_result_frame, quantize, tape

# The top's OUTPUTS parameter (8 on the chip); test/top/run.py --outputs sets both.
OUTPUTS = int(os.environ.get("OUTPUTS", "8"))
SMOLLM = Path(__file__).resolve().parents[2] / "build/smollm_attention.npz"  # python/smollm_extract.py

def pad(row):
    """A short Q/K/V row, zero-extended to 64 components."""
    return list(row) + [0] * (64 - len(row))


# TT QSPI Pmod on uio: CS0# (flash), IO0, IO1, SCK, IO2, IO3, CS1#, CS2# (RAMs).
IO_PINS = (1, 2, 4, 5)  # IO0..IO3


class Flash:
    """W25Q128JV Fast Read Quad Output (0x6B): command and 24-bit address on IO0, 8 dummy
    clocks, then nibbles in order on IO3..IO0 (high nibble first) until CS# rises. The
    outputs change after each SCK falling edge; undriven lines read as junk."""

    def __init__(self, rng):
        self.rng = rng
        self.memory = [0]
        self.prev_cs = 1
        self.prev_sck = 0
        self.prev_io0 = 0
        self.bits = 0               # SCK rises since CS# fell
        self.command_address = 0
        self.nibble = None          # driven on IO3..IO0, or None when high-Z

    def pins(self):
        """uio_in: the driven nibble on the IO pins, junk on undriven ones."""
        value = self.rng.getrandbits(8)
        if self.nibble is not None:
            for lane, pin in enumerate(IO_PINS):
                value = value & ~(1 << pin) | (self.nibble >> lane & 1) << pin
        return value

    def observe(self, cs, sck, io0, io0_oe):
        """Pins in the clk cycle just started; the flash acts on its SCK and CS# edges."""
        assert not (sck and (cs or self.prev_cs)), "SCK high while CS# high or falling (mode 0)"
        if self.prev_cs and not cs:
            self.bits = 0
            self.command_address = 0
        if cs:
            self.nibble = None
        elif not self.prev_sck and sck:
            if self.bits < 32:
                assert io0_oe, f"IO0 not driven for command bit {self.bits}"
                assert io0 == self.prev_io0, f"IO0 changes at SCK rise {self.bits}"
                self.command_address = (self.command_address << 1) | io0
            self.bits += 1
            if self.bits == 32:
                assert self.command_address == 0x6B000000, f"flash command {self.command_address:#010x}"
        elif self.prev_sck and not sck and self.bits >= 40:
            index = self.bits - 40  # after the 8th dummy clock
            address = (self.command_address & 0xFFFFFF) + index // 2
            self.nibble = (self.memory[address] >> (0 if index % 2 else 4) & 0xF
                           if address < len(self.memory) else self.rng.getrandbits(4))
        # No contention: IO0 is released by the first dummy clock and never driven deselected.
        if cs or self.bits > 32:
            assert not io0_oe, f"IO0 driven at SCK rise {self.bits}, CS# {cs}"
        assert not (io0_oe and self.nibble is not None), "IO0 contention"
        self.prev_cs = cs
        self.prev_sck = sck
        self.prev_io0 = io0


CLK_PS = 10_000  # 10 ns clk; the SPI host below is timed independently of it
PROFILES = ("limit", "aligned", "jitter", "slow")


class Harness:
    """Pins of the TT top: the flash model is clocked by clk, the SPI host runs on its own timers."""

    def __init__(self, dut):
        self.dut = dut
        self.rng = random.Random(8)  # host timing, junk bits, busy writes
        self.flash = Flash(random.Random(9))
        self.cycles = 0
        self.ui = 0b100  # ui_in: SCK low, MOSI low, CS# high
        self.runs = 0
        self.profile = PROFILES[0]
        cocotb.start_soon(self.clock_side())

    async def clock_side(self):
        d = self.dut
        while True:
            await FallingEdge(d.clk)
            d.uio_in.value = self.flash.pins()
            await RisingEdge(d.clk)
            await Timer(1, unit="ns")
            oe, out = int(d.uio_oe.value), d.uio_out.value
            # Outputs: CS0#, SCK, and CS1#/CS2# held high (the Pmod has no pull-ups on
            # them). IO1..IO3 are always inputs; IO0 is checked by the flash, and its
            # output value only while driven.
            assert oe & 0xFD == 0xC9, f"pin directions {oe:#04x}"
            assert int(out[7]) == int(out[6]) == 1, "RAM chip selects not high"
            assert int(d.uo_out.value) >> 2 == 0, "unused outputs not 0"
            io0_oe = oe >> 1 & 1
            self.flash.observe(int(out[0]), int(out[3]), int(out[1]) if io0_oe else 0, io0_oe)
            self.cycles += 1

    def drdy(self):
        return int(self.dut.uo_out.value[1])

    def set_pins(self, sck=None, mosi=None, cs=None):
        for bit, level in ((0, sck), (1, mosi), (2, cs)):
            if level is not None:
                self.ui = self.ui & ~(1 << bit) | level << bit
        self.dut.ui_in.value = self.ui

    def phase(self):
        """One SCK or CS# level in ps. The limit is 4 clk; the host is not related to clk."""
        if self.profile in ("limit", "aligned"):
            return 4 * CLK_PS                        # SCK = clk / 8 exactly
        if self.profile == "slow":
            return 103_700                           # 10.37 clk: SCK = clk / 20.74
        return self.rng.randint(4 * CLK_PS, 7 * CLK_PS)  # jittered, non-integer

    async def frame(self, word):
        """One 16-bit mode-0 frame, MSB first: send `word` on MOSI and return the MISO bits.

        Ends with CS# high for one phase (>= 4 clk), after which DRDY is valid.
        """
        if self.profile == "aligned":
            await RisingEdge(self.dut.clk)           # every pin change lands on a clk edge
        self.ui = self.rng.randrange(32) << 3 | self.ui & 7  # unused ui_in bits are junk
        self.set_pins(cs=0, mosi=word >> 15 & 1)
        received = 0
        for i in range(16):
            await Timer(self.phase(), unit="ps")     # SCK low (the first: CS# fall to SCK rise)
            self.set_pins(sck=1)
            received = received << 1 | int(self.dut.uo_out.value[0])
            await Timer(self.phase(), unit="ps")     # SCK high
            # MOSI changes right at the falling edge; after the last bit it is junk.
            self.set_pins(sck=0, mosi=word >> (14 - i) & 1 if i < 15 else self.rng.randrange(2))
        if self.profile == "jitter":
            await Timer(self.rng.randrange(3 * CLK_PS), unit="ps")
        self.set_pins(cs=1)                          # at the limit, together with the last SCK fall
        await Timer(self.phase(), unit="ps")
        return received

    async def wait_drdy(self, name):
        start = self.cycles
        while not self.drdy():
            assert self.cycles - start < 200000, f"{name}: timeout waiting for DRDY"
            await Timer(self.rng.randint(CLK_PS, 20 * CLK_PS), unit="ps")

    async def run(self, n, shift, cont, expected, name):
        """One run: a config frame, then one result frame per component (OUTPUTS) while DRDY is high."""
        self.profile = PROFILES[self.runs % len(PROFILES)]
        self.runs += 1
        await self.frame(config_frame(n, shift, cont))
        if self.rng.randrange(2):
            # A config write while busy (DRDY low throughout) is ignored.
            assert not self.drdy(), f"{name}: DRDY right after start"
            await self.frame(config_frame(self.rng.randint(1, 16), self.rng.randrange(16), 1 - cont))
            assert not self.drdy(), f"{name}: busy config write overlapped DRDY"
        actual = []
        for component in range(OUTPUTS):
            await self.wait_drdy(f"{name} component {component}")
            # SCK edges while deselected (CS# high) must be ignored.
            for _ in range(self.rng.randrange(3)):
                self.set_pins(sck=1); await Timer(self.phase(), unit="ps")
                self.set_pins(sck=0); await Timer(self.phase(), unit="ps")
            actual.append(decode_result_frame(await self.frame(self.rng.getrandbits(16))))
            assert not self.drdy(), f"{name}: DRDY still high 4 clk after the read"
        # After the last read the chip is idle: no further division raises DRDY (one takes about 25 clk).
        for _ in range(40):
            await RisingEdge(self.dut.clk)
            assert not self.drdy(), f"{name}: DRDY after {OUTPUTS} reads"
        assert actual == expected, f"{name} (N={n}, {self.profile}): hardware={actual}, Python={expected}"

    async def head(self, q, k, v, shift=0, chunks=(0,), *, name="query"):
        """q: 64 ints; k, v: N rows of 64. Runs the chunks in order: one fresh run, then cont runs.

        Chunk numbers are taken modulo 64 / OUTPUTS, so the same tests run at every OUTPUTS."""
        q, k, v = pad(q), [pad(r) for r in k], [pad(r) for r in v]
        chunks = [c % (64 // OUTPUTS) for c in chunks]
        self.flash.memory = tape(q, k, v, chunks, OUTPUTS)
        start = self.cycles
        for i, chunk in enumerate(chunks):
            expected = chip_attention(q, k, [row[OUTPUTS*chunk:OUTPUTS*(chunk + 1)] for row in v], score_shift=shift)
            await self.run(len(k), shift, int(i > 0), expected, f"{name} chunk {chunk}")
            # The chip clocks exactly the bits of the tape so far, and never restarts mid-head.
            consumed = 128 * len(k) * (2 + i) + OUTPUTS * len(k) * (1 + i)
            assert self.flash.bits == 40 + 2 * consumed, f"{name}: {self.flash.bits - 40} tape nibbles read"
        assert consumed == len(self.flash.memory)
        self.dut._log.info("%s (N=%d, shift=%d, chunks=%s): matches Python, %d cycles",
                           name, len(k), shift, list(chunks), self.cycles - start)

    async def query(self, q, k, v, shift=0, chunk=0, *, name="query"):
        await self.head(q, k, v, shift, (chunk,), name=name)

    async def abort(self, signal):
        """Hold rst_n or ena low for 3 clk with CS# high; the flash must be released."""
        d = self.dut
        await FallingEdge(d.clk)
        getattr(d, signal).value = 0
        for _ in range(3):
            await FallingEdge(d.clk)
        getattr(d, signal).value = 1
        assert self.flash.prev_cs == 1, f"{signal} low did not release flash CS"

    async def wait_flash(self, done, what):
        for _ in range(1000):
            await RisingEdge(self.dut.clk)
            await Timer(2, unit="ns")
            if done():
                return
        assert False, what


async def start_harness(dut):
    """Power-up: rst_n low for exactly 3 clk (the documented minimum) with CS# high."""
    dut.rst_n.value = 0
    dut.ena.value = 1
    dut.ui_in.value = 0b100
    dut.uio_in.value = 0
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    h = Harness(dut)
    for _ in range(3):
        await FallingEdge(dut.clk)
    dut.rst_n.value = 1
    return h


@cocotb.test()
async def end_to_end_flash_and_host(dut):
    h = await start_harness(dut)
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
    await h.frame(config_frame(1, 0, 0))
    await h.wait_flash(lambda: not h.flash.prev_cs and h.flash.bits >= 12, "flash read never started")
    await h.abort("rst_n")
    await h.query([0, 0, 0, 0], [[0, 0, 0, 0]], [[127, -128, 1, -1]])
    await h.frame(config_frame(1, 0, 0))
    await h.wait_flash(lambda: not h.flash.prev_cs and h.flash.bits >= 12,
                       "flash read never started before ena abort")
    await h.abort("ena")
    await h.query([0, 0, 0, 0], [[0, 0, 0, 0]], [[-1, 0, 1, 127]])
    # Abort in the dummy clocks and in the data, just after the flash starts driving.
    for bits in (36, 41):
        await h.frame(config_frame(1, 0, 0))
        await h.wait_flash(lambda: not h.flash.prev_cs and h.flash.bits >= bits, f"flash never reached rise {bits}")
        await h.abort("rst_n")
        await h.query([3, 0, 0, 0], [[5, 0, 0, 0]], [[-7, 9, 11, -13]])
    dut._log.info("PASS top: tape reads, SPI target frames at and above the SCK limit, "
                  "busy config writes, reset/ena abort; %d cycles", h.cycles)


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
    before = h.flash.bits
    await h.frame(config_frame(3, 12, 1))
    await h.wait_flash(lambda: h.flash.bits > before + 64, "cont run did not clock the flash")
    assert h.flash.prev_cs == 0, "cont run dropped the flash read"
    await h.abort("rst_n")
    await h.query(vec(), [vec() for _ in range(2)], [vec() for _ in range(2)], 14, 3, name="after abort")


@cocotb.test(skip=not SMOLLM.exists())
async def real_smollm_head(dut):
    """One real SmolLM-135M head (layer 14, head 4, last of 16 tokens) through the pins."""
    import numpy as np
    data = np.load(SMOLLM)
    prompt, layer, head, chunk = 0, 14, 4, 5 % (64 // OUTPUTS)
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
    got = chip_attention(qi.tolist(), ki.tolist(), [r[OUTPUTS*chunk:OUTPUTS*(chunk + 1)] for r in vi.tolist()],
                         score_shift=shift)  # = the RTL, asserted inside query()
    est = np.array(got) / 16 * 2.0 ** -ev[0, OUTPUTS*chunk:OUTPUTS*(chunk + 1)]
    dut._log.info("SmolLM float output %s, chip %s", np.round(ref[OUTPUTS*chunk:OUTPUTS*(chunk + 1)], 4), np.round(est, 4))
