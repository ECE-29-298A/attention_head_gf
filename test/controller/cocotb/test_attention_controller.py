"""Directed and seeded-random tests for the two-pass INT4 controller."""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

from attention_model import chip_attention, divide_round, dot4, exp_weight, pack_byte


def packed(row):
    return sum((v & 15) << (4 * i) for i, v in enumerate(row))


class Bus:
    def __init__(self, dut, seed=298):
        self.dut = dut
        self.rng = random.Random(seed)
        self.cycle = 0
        self.memory = {}
        self.mem_pending = None
        self.exp_pending = None
        self.div_pending = None
        self.reads = []
        self.exps = []
        self.divs = []
        self.outputs = []
        self.mem_stall_addr = None
        self.out_stall_data = None

    async def tick(self, *, start=0, count=1, query=0, reset=1,
                   mem_ready=None, out_ready=None, delay=None):
        d = self.dut
        await FallingEdge(d.clk)
        d.rst_n.value = reset
        d.start.value = start
        d.token_count.value = count
        d.query_packed.value = query
        d.mem_req_ready.value = self.rng.randrange(4) != 0 if mem_ready is None else mem_ready
        d.out_ready.value = self.rng.randrange(3) != 0 if out_ready is None else out_ready
        mem_due = self.mem_pending is not None and self.mem_pending[0] <= self.cycle
        exp_due = self.exp_pending is not None and self.exp_pending[0] <= self.cycle
        div_due = self.div_pending is not None and self.div_pending[0] <= self.cycle
        d.mem_rsp_valid.value = int(mem_due and reset)
        d.mem_rdata.value = self.mem_pending[1] if mem_due and reset else 0
        await Timer(1, unit="ns")
        req = reset and int(d.mem_req_valid.value)
        addr = int(d.mem_addr.value) if reset else 0
        req_ready = int(d.mem_req_ready.value)
        exp_start = reset and int(d.exp_start.value)
        div_start = reset and int(d.div_start.value)
        out_valid = reset and int(d.out_valid.value)
        out_data = int(d.out_data.value.to_signed()) if reset else 0
        ready = int(d.out_ready.value)
        exp_args = (int(d.exp_max.value.to_signed()), int(d.exp_score.value.to_signed())) if reset else (0, 0)
        div_args = (int(d.div_sum.value.to_signed()), int(d.div_denominator.value)) if reset else (0, 0)
        if reset:
            assert int(d.exp_done.value) == int(exp_due), "LUT completion timing"
            assert int(d.div_done.value) == int(div_due), "divider completion timing"
            if exp_due:
                assert int(d.exp_weight.value) == self.exp_pending[1], "LUT result mismatch"
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
            self.mem_pending = self.exp_pending = self.div_pending = None
            self.mem_stall_addr = self.out_stall_data = None
        else:
            if mem_due:
                self.mem_pending = None
            if exp_due:
                self.exp_pending = None
            if div_due:
                self.div_pending = None
            if req and req_ready:
                assert self.mem_pending is None, "more than one memory read outstanding"
                assert addr in self.memory, f"read outside K/V memory: 0x{addr:x}"
                self.reads.append(addr)
                self.mem_pending = (self.cycle + (delay or self.rng.randint(1, 5)), self.memory[addr])
            if exp_start:
                assert self.exp_pending is None
                self.exps.append(exp_args)
                self.exp_pending = (self.cycle + 1, exp_weight(*exp_args))
            if div_start:
                assert self.div_pending is None
                self.divs.append(div_args)
                self.div_pending = (self.cycle + 21, divide_round(*div_args))
            if out_valid and ready:
                self.outputs.append(out_data)
        self.cycle += 1

    async def reset(self):
        await self.tick(reset=0, mem_ready=0, out_ready=0)
        await self.tick(reset=0, mem_ready=0, out_ready=0)
        assert int(self.dut.busy.value) == 0
        assert int(self.dut.done.value) == 0
        self.reads.clear(); self.exps.clear(); self.divs.clear(); self.outputs.clear()

    def load(self, keys, values):
        self.memory = {}
        for base, rows in ((0, keys), (32, values)):
            for i, row in enumerate(rows):
                self.memory[base + 2*i] = pack_byte(row[0], row[1])
                self.memory[base + 2*i + 1] = pack_byte(row[2], row[3])

    async def run_case(self, q, keys, values, *, delay=None, force_stalls=False):
        n = len(keys)
        self.load(keys, values)
        self.reads.clear(); self.exps.clear(); self.divs.clear(); self.outputs.clear()
        self.mem_stall_addr = self.out_stall_data = None
        await self.tick(start=0, count=n, query=packed(q))
        assert int(self.dut.start_ready.value) == 1
        await self.tick(start=1, count=n, query=packed(q))
        assert int(self.dut.busy.value) == 1
        forced_mem = forced_out = False
        for _ in range(3000):
            # Inputs are deliberately corrupted after acceptance: Q and N must be latched.
            if force_stalls and not forced_mem and int(self.dut.mem_req_valid.value):
                await self.tick(count=0, query=0xffff, mem_ready=0, delay=delay)
                await self.tick(count=0, query=0xffff, mem_ready=0, delay=delay)
                forced_mem = True
            elif force_stalls and not forced_out and int(self.dut.out_valid.value):
                await self.tick(count=0, query=0xffff, out_ready=0, delay=delay)
                await self.tick(count=0, query=0xffff, out_ready=0, delay=delay)
                forced_out = True
            else:
                await self.tick(count=0, query=0xffff, delay=delay)
            if int(self.dut.done.value):
                break
        else:
            assert False, "controller timed out"
        if force_stalls:
            assert forced_mem and forced_out, "directed stall phases not reached"
        scores = [dot4(q, k) for k in keys]
        maximum = max(scores)
        weights = [exp_weight(maximum, s) for s in scores]
        denominator = sum(weights)
        sums = [sum(w * v[i] for w, v in zip(weights, values)) for i in range(4)]
        assert self.exps == list(zip([maximum]*n, scores))
        assert self.divs == list(zip(sums, [denominator]*4))
        assert self.outputs == chip_attention(q, keys, values)
        assert self.reads == [addr for i in range(n) for addr in (2*i, 2*i+1)] + [
            addr for i in range(n) for addr in (2*i, 2*i+1, 32+2*i, 33+2*i)]
        await self.tick(count=0, query=0, out_ready=0)
        assert int(self.dut.done.value) == 1 and int(self.dut.out_valid.value) == 0


@cocotb.test()
async def directed_and_random_queries(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    bus = Bus(dut)
    await bus.reset()
    cases = [
        ([1, 0, 0, 0], [[-8, 0, 0, 0]], [[-8, -1, 0, 7]]),
        ([-8]*4, [[-8]*4]*16, [[-8]*4]*16),
        ([-8]*4, [[7]*4]*16, [[7]*4]*16),
        ([0]*4, [[0]*4]*2, [[0]*4, [1]*4]),
        ([1, 0, 0, 0], [[x, 0, 0, 0] for x in range(-8, 8)],
         [[-8, 7, -1, 1] if x & 1 else [7, -8, 1, -1] for x in range(16)]),
    ]
    rng = random.Random(2026)
    for n in range(1, 17):
        for _ in range(3):
            vec = lambda: [rng.randint(-8, 7) for _ in range(4)]
            cases.append((vec(), [vec() for _ in range(n)], [vec() for _ in range(n)]))
    for index, (q, keys, values) in enumerate(cases):
        await bus.run_case(q, keys, values, force_stalls=index == 0)


@cocotb.test()
async def invalid_count_and_reset_abort(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    bus = Bus(dut, seed=77)
    await bus.reset()
    for bad in (0, 17, 31):
        await bus.tick(start=1, count=bad)
        assert int(dut.start_ready.value) == 0 and int(dut.busy.value) == 0
    q = [1, 0, 0, 0]
    keys = [[1, 0, 0, 0], [2, 0, 0, 0]]
    values = [[1, 2, 3, 4], [4, 3, 2, 1]]
    bus.load(keys, values)
    await bus.tick(start=1, count=2, query=packed(q))
    assert int(dut.busy.value)
    # Reset with an outstanding read. The testbench discards its pending response.
    for _ in range(100):
        await bus.tick(count=2, query=packed(q), delay=8)
        if bus.mem_pending:
            break
    assert bus.mem_pending
    await bus.reset()
    await bus.run_case(q, keys, values, delay=2)

    # Abort independently while the exponent or divider is pending, and while
    # the final output is stalled. Each fresh query must be unaffected.
    for phase in ("exp", "div", "out"):
        bus.load(keys, values)
        await bus.tick(start=1, count=2, query=packed(q))
        assert int(dut.busy.value)
        for _ in range(1000):
            await bus.tick(count=2, query=packed(q), out_ready=0, delay=2)
            if ((phase == "exp" and bus.exp_pending) or
                (phase == "div" and bus.div_pending) or
                (phase == "out" and int(dut.out_valid.value))):
                break
        else:
            assert False, f"never reached {phase} phase"
        await bus.reset()
        await bus.run_case(q, keys, values, delay=2)
