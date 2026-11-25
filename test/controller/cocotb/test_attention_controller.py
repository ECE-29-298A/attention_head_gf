"""Directed and seeded-random tests for the two-pass INT8 controller.

64-dim scores (one Q byte then one K byte per dimension), one 2-wide V chunk per
run, rounded score shift, 12-bit outputs sent as two bytes each.
"""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

from attention_model import chip_attention, divide_round, dot, exp_weight, pack_byte

Q_BASE, K_BASE, V_BASE = 0x000, 0x040, 0x440


def words(output_bytes):
    """Signed output bytes, low byte first, to the four signed 16-bit results."""
    return [(hi << 8) | (lo & 255) for lo, hi in zip(output_bytes[::2], output_bytes[1::2])]


class Bus:
    def __init__(self, dut, seed=298):
        self.dut = dut
        self.rng = random.Random(seed)
        self.cycle = 0
        self.memory = {}
        self.mem_pending = None
        self.div_pending = None
        self.reads = []
        self.exps = []
        self.divs = []
        self.outputs = []
        self.mem_stall_addr = None
        self.out_stall_data = None
        self.shift = 0  # the latched score shift of the running query

    async def tick(self, *, start=0, count=1, shift=0, chunk=0, reset=1,
                   mem_ready=None, out_ready=None, delay=None):
        d = self.dut
        await FallingEdge(d.clk)
        d.rst_n.value = reset
        d.start.value = start
        d.token_count.value = count
        d.score_shift.value = shift
        d.chunk.value = chunk
        d.mem_req_ready.value = self.rng.randrange(4) != 0 if mem_ready is None else mem_ready
        d.out_ready.value = self.rng.randrange(3) != 0 if out_ready is None else out_ready
        mem_due = self.mem_pending is not None and self.mem_pending[0] <= self.cycle
        div_due = self.div_pending is not None and self.div_pending[0] <= self.cycle
        d.mem_rsp_valid.value = int(mem_due and reset)
        d.mem_rdata.value = self.mem_pending[1] if mem_due and reset else 0
        await Timer(1, unit="ns")
        req = reset and int(d.mem_req_valid.value)
        addr = int(d.mem_addr.value) if reset else 0
        req_ready = int(d.mem_req_ready.value)
        # Pass 2 starts each score at M and subtracts. The edge after its final
        # MAC leaves D = M - S, and the combinational LUT weight must match it.
        exp_ready = reset and int(d.mac.score_en.value) and int(d.second_pass.value) and \
            int(d.bit_index.value) == 7 and int(d.dim.value) == 63
        div_start = reset and int(d.div_start.value)
        out_valid = reset and int(d.out_valid.value)
        out_data = int(d.out_data.value.to_signed()) if reset else 0
        ready = int(d.out_ready.value)
        # The accum ring has no reset (X until loaded), so only sample it on a start.
        div_args = (int(d.div_sum.value.to_signed()), int(d.div_denominator.value)) if div_start else (0, 0)
        if reset:
            assert int(d.div_done.value) == int(div_due), "divider completion timing"
            if div_due:
                assert d.div_result.value.to_signed() == self.div_pending[1], "divider result mismatch"
        if self.mem_stall_addr is not None:
            assert req and addr == self.mem_stall_addr, "memory request changed while stalled"
        self.mem_stall_addr = addr if req and not req_ready else None
        if self.out_stall_data is not None:
            assert out_valid and out_data == self.out_stall_data, "output changed while stalled"
        self.out_stall_data = out_data if out_valid and not ready else None
        assert int(d.mem_write.value) == 0 and int(d.mem_wdata.value) == 0
        await RisingEdge(d.clk)
        await Timer(1, unit="ns")
        if not reset:
            self.mem_pending = self.div_pending = None
            self.mem_stall_addr = self.out_stall_data = None
        else:
            if mem_due:
                self.mem_pending = None
            if div_due:
                self.div_pending = None
            if req and req_ready:
                assert self.mem_pending is None, "more than one memory read outstanding"
                assert addr in self.memory, f"read outside K/V memory: 0x{addr:x}"
                self.reads.append(addr)
                self.mem_pending = (self.cycle + (delay or self.rng.randint(1, 5)), self.memory[addr])
            if exp_ready:
                maximum = d.maximum.value.to_signed()
                score = maximum - int(d.exp_delta.value)
                self.exps.append((maximum, score))
                assert int(d.exp_weight.value) == exp_weight(maximum, score, score_shift=self.shift), \
                    "LUT result mismatch"
            if div_start:
                assert self.div_pending is None
                self.divs.append(div_args)
                self.div_pending = (self.cycle + 25, divide_round(*div_args))
            if out_valid and ready:
                self.outputs.append(out_data)
        self.cycle += 1

    async def reset(self):
        await self.tick(reset=0, mem_ready=0, out_ready=0)
        await self.tick(reset=0, mem_ready=0, out_ready=0)
        assert int(self.dut.busy.value) == 0
        assert int(self.dut.done.value) == 0
        self.reads.clear(); self.exps.clear(); self.divs.clear(); self.outputs.clear()

    def load(self, q, keys, values):
        """Q (64), then N rows of 64 K and 64 V components."""
        self.memory = {Q_BASE + j: pack_byte(x) for j, x in enumerate(q)}
        for base, rows in ((K_BASE, keys), (V_BASE, values)):
            for i, row in enumerate(rows):
                for j, v in enumerate(row):
                    self.memory[base + 64*i + j] = pack_byte(v)

    async def run_case(self, q, keys, values, shift=0, chunk=0, *, delay=None, force_stalls=False):
        n = len(keys)
        self.load(q, keys, values)
        self.shift = shift
        self.reads.clear(); self.exps.clear(); self.divs.clear(); self.outputs.clear()
        self.mem_stall_addr = self.out_stall_data = None
        await self.tick(start=0, count=n, shift=shift, chunk=chunk)
        assert int(self.dut.start_ready.value) == 1
        await self.tick(start=1, count=n, shift=shift, chunk=chunk)
        assert int(self.dut.busy.value) == 1
        forced_mem = forced_out = False
        bad = dict(count=0, shift=~shift & 15, chunk=~chunk & 31)
        for _ in range(400000):
            # Inputs are deliberately corrupted after acceptance: N, shift and chunk must be latched.
            if force_stalls and not forced_mem and int(self.dut.mem_req_valid.value):
                await self.tick(**bad, mem_ready=0, delay=delay)
                await self.tick(**bad, mem_ready=0, delay=delay)
                forced_mem = True
            elif force_stalls and not forced_out and int(self.dut.out_valid.value):
                await self.tick(**bad, out_ready=0, delay=delay)
                await self.tick(**bad, out_ready=0, delay=delay)
                forced_out = True
            else:
                await self.tick(**bad, delay=delay)
            if int(self.dut.done.value):
                break
        else:
            assert False, "controller timed out"
        if force_stalls:
            assert forced_mem and forced_out, "directed stall phases not reached"
        scores = [dot(q, k) for k in keys]
        maximum = max(scores)
        weights = [exp_weight(maximum, s, score_shift=shift) for s in scores]
        denominator = sum(weights)
        chunk_v = [row[2*chunk:2*chunk + 2] for row in values]
        sums = [sum(w * v[i] for w, v in zip(weights, chunk_v)) for i in range(2)]
        assert self.exps == list(zip([maximum]*n, scores))
        assert self.divs == list(zip(sums, [denominator]*2))
        assert len(self.outputs) == 4 and words(self.outputs) == chip_attention(
            q, keys, chunk_v, score_shift=shift)
        # Per token: 64 dimensions of one Q byte then one K byte; pass 2 adds the V chunk.
        score_reads = lambda i: [base + off + j for j in range(64)
                                 for base, off in ((Q_BASE, 0), (K_BASE, 64*i))]
        assert self.reads == [a for i in range(n) for a in score_reads(i)] + [
            a for i in range(n)
            for a in score_reads(i) + [V_BASE + 64*i + 2*chunk + j for j in range(2)]]
        await self.tick(count=0, out_ready=0)
        assert int(self.dut.done.value) == 1 and int(self.dut.out_valid.value) == 0


@cocotb.test()
async def directed_and_random_queries(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    bus = Bus(dut)
    await bus.reset()
    rng = random.Random(2026)
    vec = lambda lo=-128, hi=127: [rng.randint(lo, hi) for _ in range(64)]
    pad = lambda row: row + [0] * (64 - len(row))
    e1 = pad([1])
    cases = [
        (e1, [pad([-128])], [vec()], 0, 0),
        ([-128]*64, [[-128]*64]*16, [[-128]*64]*16, 15, 31),
        ([-128]*64, [[127]*64]*16, [[127]*64]*16, 0, 3),
        ([0]*64, [[0]*64]*2, [[0]*64, [1]*64], 0, 18),
        # Max changes at the last key; rounding ties at shift 2 (D = 2, 6, 10 -> 1, 2, 3).
        (e1, [pad([x]) for x in range(-8, 8)], [vec() for _ in range(16)], 2, 5),
    ]
    for n in (1, 2, 5, 9, 16):
        cases.append((vec(), [vec() for _ in range(n)], [vec() for _ in range(n)],
                      rng.randint(10, 15), rng.randrange(32)))
        cases.append((vec(-40, 40), [vec(-40, 40) for _ in range(n)], [vec() for _ in range(n)],
                      rng.randint(4, 12), rng.randrange(32)))
    for index, (q, keys, values, shift, chunk) in enumerate(cases):
        await bus.run_case(q, keys, values, shift, chunk, force_stalls=index == 0)


@cocotb.test()
async def invalid_count_and_reset_abort(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    bus = Bus(dut, seed=77)
    await bus.reset()
    for bad in (0, 17, 31):
        await bus.tick(start=1, count=bad)
        assert int(dut.start_ready.value) == 0 and int(dut.busy.value) == 0
    q = [1] + [0] * 63
    keys = [[1] + [0] * 63, [2] + [0] * 63]
    values = [[1, 2, 3, 4] * 16, [4, 3, 2, 1] * 16]
    bus.load(q, keys, values)
    await bus.tick(start=1, count=2)
    assert int(dut.busy.value)
    # Reset with an outstanding read. The testbench discards its pending response.
    for _ in range(100):
        await bus.tick(count=2, delay=8)
        if bus.mem_pending:
            break
    assert bus.mem_pending
    await bus.reset()
    await bus.run_case(q, keys, values, delay=2)

    # Abort independently while a pass-2 weight is live, while the divider is
    # pending, and while the final output is stalled. Each fresh query must be unaffected.
    for phase in ("exp", "div", "out"):
        bus.load(q, keys, values)
        await bus.tick(start=1, count=2)
        assert int(dut.busy.value)
        for _ in range(100000):
            await bus.tick(count=2, out_ready=0, delay=2)
            if ((phase == "exp" and bus.exps) or
                (phase == "div" and bus.div_pending) or
                (phase == "out" and int(dut.out_valid.value))):
                break
        else:
            assert False, f"never reached {phase} phase"
        await bus.reset()
        await bus.run_case(q, keys, values, delay=2)
