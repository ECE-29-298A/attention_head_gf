"""Pin-level, cycle-exact checks shared by the QSPI and OSPI top modules."""

import random

import cocotb
from cocotb.triggers import Timer


async def tick(dut):
    """One 10 ns system clock period; return after registered outputs settle."""
    dut.clk.value = 0
    await Timer(5, unit="ns")
    dut.clk.value = 1
    await Timer(5, unit="ns")


def value(signal):
    return int(signal.value)


async def reset(dut):
    dut.clk.value = 0
    dut.rst_n.value = 0
    dut.start.value = 0
    dut.wide.value = 0
    dut.tx_en.value = 0
    dut.last.value = 0
    dut.tx_data.value = 0
    dut.io_i.value = 0
    await Timer(1, unit="ns")
    assert value(dut.cs_n) == 1
    assert value(dut.sck) == 0
    assert value(dut.ready) == 1
    assert value(dut.done) == 0
    assert value(dut.io_oe) == 0
    await tick(dut)
    dut.rst_n.value = 1


async def transfer(dut, *, wide, tx_en, last, tx, rx, busy_start=False):
    lanes = len(dut.io_i)
    width = lanes if wide else 1
    beats = 8 // width
    mask = (1 << width) - 1
    expected_oe = ((1 << lanes) - 1 if wide else 1) if tx_en else 0

    assert value(dut.ready) == 1
    assert value(dut.sck) == 0
    dut.start.value = 1
    dut.wide.value = wide
    dut.tx_en.value = tx_en
    dut.last.value = last
    dut.tx_data.value = tx
    await tick(dut)
    assert value(dut.ready) == 0
    assert value(dut.cs_n) == 0
    assert value(dut.sck) == 0
    assert value(dut.io_oe) == expected_oe

    for beat in range(beats):
        shift = 8 - (beat + 1) * width
        expected_tx = (tx >> shift) & mask
        incoming = (rx >> shift) & mask
        dut.io_i.value = incoming if wide else incoming << 1

        # Change the request inputs after acceptance. The current byte must
        # retain the accepted mode, direction, data, and chip-select policy.
        dut.start.value = int(busy_start and beat == 0)
        dut.wide.value = int(not wide)
        dut.tx_en.value = int(not tx_en)
        dut.last.value = int(not last)
        dut.tx_data.value = tx ^ 0xFF
        await Timer(1, unit="ns")
        assert value(dut.io_o) == expected_tx, f"TX beat {beat}"
        assert value(dut.io_oe) == expected_oe, f"OE beat {beat}"

        await tick(dut)  # SCK rises; input lanes are sampled.
        assert value(dut.sck) == 1, f"SCK rise {beat}"
        assert value(dut.ready) == 0
        assert value(dut.done) == 0
        assert value(dut.cs_n) == 0

        await tick(dut)  # SCK falls; shifter advances.
        assert value(dut.sck) == 0, f"SCK fall {beat}"
        assert value(dut.ready) == 0
        assert value(dut.done) == 0

    dut.start.value = 0
    await tick(dut)  # Post-clock hold period and completion.
    assert value(dut.done) == 1
    assert value(dut.ready) == 1
    assert value(dut.sck) == 0
    assert value(dut.cs_n) == int(last)
    assert value(dut.rx_data) == rx, f"RX: got {value(dut.rx_data):02x}, expected {rx:02x}"
    if last:
        assert value(dut.io_oe) == 0
    await tick(dut)
    assert value(dut.done) == 0
    assert value(dut.ready) == 1
    assert value(dut.cs_n) == int(last)


@cocotb.test()
async def test_byte_modes_and_continuous_chip_select(dut):
    await reset(dut)

    # Command, mode change, read turnaround, and output in one CS window.
    await transfer(dut, wide=False, tx_en=True, last=False,
                   tx=0x9F, rx=0xA5, busy_start=True)
    await transfer(dut, wide=True, tx_en=False, last=False,
                   tx=0x00, rx=0x3C)
    await transfer(dut, wide=True, tx_en=True, last=True,
                   tx=0xD2, rx=0x5A)
    await transfer(dut, wide=False, tx_en=False, last=True,
                   tx=0x00, rx=0xC7)

    rng = random.Random(0x180)
    for index in range(24):
        await transfer(dut, wide=bool(index & 1), tx_en=bool(index & 2),
                       last=(index % 4 == 3), tx=rng.randrange(256),
                       rx=rng.randrange(256), busy_start=bool(index & 4))


@cocotb.test()
async def test_async_reset_aborts_and_recovers(dut):
    await reset(dut)
    dut.start.value = 1
    dut.wide.value = 1
    dut.tx_en.value = 1
    dut.last.value = 0
    dut.tx_data.value = 0x69
    await tick(dut)
    assert value(dut.cs_n) == 0
    assert value(dut.ready) == 0

    dut.start.value = 0
    dut.rst_n.value = 0
    await Timer(1, unit="ns")  # No clock edge: reset must act asynchronously.
    assert value(dut.cs_n) == 1
    assert value(dut.sck) == 0
    assert value(dut.ready) == 1
    assert value(dut.done) == 0
    assert value(dut.io_oe) == 0

    await tick(dut)
    dut.rst_n.value = 1
    await transfer(dut, wide=True, tx_en=False, last=True,
                   tx=0x00, rx=0x96)
