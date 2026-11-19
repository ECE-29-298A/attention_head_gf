"""End-to-end Tiny Tapeout top test with a bit-accurate 0x03 flash model."""
import random
import sys
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python/src"))
from attention_model import chip_attention, pack_byte


class Flash:
    def __init__(self):
        self.memory = [0] * 128
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

    async def query(self, q, k, v):
        n = len(k)
        self.flash.memory = [0] * 128
        for t in range(n):
            for c in range(4):
                self.flash.memory[4*t+c] = pack_byte(k[t][c])
                self.flash.memory[64+4*t+c] = pack_byte(v[t][c])
        first_read = len(self.flash.reads)
        await self.send(n)
        for value in q:
            await self.send(pack_byte(value))

        expected = [pack_byte(x) for x in chip_attention(q, k, v)]
        for index, wanted in enumerate(expected):
            for _ in range(30000):
                valid, data = await self.tick(host=0)
                if valid:
                    break
            else:
                assert False, f"deadlock before output {index}"
            assert data == wanted, (index, data, wanted)
            for _ in range(3):
                held_valid, held_data = await self.tick(host=0)
                assert held_valid and held_data == wanted, "output changed under backpressure"
            valid, data = await self.tick(host=1)
            assert valid and data == wanted, "output transfer mismatch"

        expected_reads = [4*t+c for t in range(n) for c in range(4)]
        for t in range(n):
            expected_reads.extend(4*t+c for c in range(4))
            expected_reads.extend(64+4*t+c for c in range(4))
        assert self.flash.reads[first_read:] == expected_reads, "K/V read order or count"


@cocotb.test()
async def end_to_end_flash_and_host(dut):
    dut.rst_n.value = 0
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0x0C
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    h = Harness(dut)
    await h.tick(reset=0)
    await h.tick(reset=0)
    for invalid in (0, 17, 255):
        ready, _ = await h.tick(data=invalid, host=1)
        assert not ready, "invalid token count accepted"

    await h.query([1, 0, 0, 0], [[-128, 0, 0, 0]], [[-128, -1, 0, 127]])
    await h.query([1, 0, 0, 0], [[0, 0, 0, 0], [1, 0, 0, 0]],
                  [[-128, 0, 127, 1], [127, 1, -128, -1]])
    rng = random.Random(298)
    q = [1, 0, 0, 0]
    k = [[t-8, 0, 0, 0] for t in range(16)]  # maximum at last token
    v = [[rng.randint(-128, 127) for _ in range(4)] for _ in range(16)]
    await h.query(q, k, v)

    # Abort after a flash transaction begins, then start a fresh query.
    await h.send(1)
    for value in (1, 0, 0, 0):
        await h.send(value)
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
    for value in (1, 0, 0, 0):
        await h.send(value)
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
    dut._log.info("PASS top: flash reads, INT8 outputs, backpressure, boundaries, reset/ena abort; %d cycles", h.cycles)
