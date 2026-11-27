#!/usr/bin/env python3
"""Classify Verilator -Wall output for attention_controller (SPEC.md R-LINT). Copied from the
frozen mac_unit contract (lint/check_lint.py, itself the divider copy); only the port list and
this text differ.

Usage: check_lint.py <verilator stderr log> <dut file> [--gate]
RTL mode: every %Warning fails, with one waiver class: UNUSEDSIGNAL ("not used" or "not
driven, nor used", i.e. a dangling net) on a signal that is NOT a
port (unused internal bits are removed by synthesis and cannot change behaviour; the golden
has two: ripple_add's dropped carry out 'c'[N] and the divider's subtractor borrow
'difference'[12], both in the frozen submodules). An unused
PORT bit is never waived. Waived lines are listed (status pass-with-waiver).
Gate mode (--gate): the DUT file is the netlist followed by the PDK cell models, separated
by the marker line written by gate/extract_cells.py. Warnings located after the marker are in
the unmodified PDK models and are listed but not counted; DECLFILENAME is a packaging artefact.
The same internal-UNUSEDSIGNAL waiver applies. Any other warning in the netlist, and any
%Error, fails.
"""
import re
import sys

MARK = "// ==== end of netlist; PDK cell models follow ===="
PORTS = {"clk", "rst_n", "start", "last", "score_shift", "cont", "idle", "spi_cs_n", "spi_sck",
         "spi_mosi", "spi_mosi_oe", "spi_io", "out_valid", "out_ready", "out_shift", "out_bit"}
log, dut = sys.argv[1], sys.argv[2]
gate = "--gate" in sys.argv[3:]
text = open(log).read()
mark = None
if gate:
    for i, l in enumerate(open(dut), 1):
        if l.rstrip() == MARK:
            mark = i
            break
    if mark is None:
        print("LINT gate mode but no end-of-netlist marker in the DUT file")
        print("RESULT lint warnings=0 netlist=0 library=0 waived=0 errors=1")
        sys.exit(1)
loc = re.compile(r"^%(Warning|Error)(-[A-Z_0-9]+)?: [^:]*:(\d+):")
unused = re.compile(r"^%Warning-UNUSEDSIGNAL: [^:]*:\d+:\d+: (?:Bits of signal are|Signal is) not (?:driven, nor )?used: '([^']+)'")
netw, libw, waived, errors = [], [], [], []
for l in text.splitlines():
    if not l.startswith("%"):
        continue
    if l.startswith("%Error"):
        if "Exiting due to" not in l:
            errors.append(l)
        continue
    if not l.startswith("%Warning"):
        continue
    m = loc.match(l)
    line = int(m.group(3)) if m else 0
    u = unused.match(l.strip())
    if gate and line > mark:
        libw.append(l)
    elif gate and l.startswith("%Warning-DECLFILENAME"):
        libw.append(l)
    elif u and u.group(1) not in PORTS:
        waived.append(l)
    else:
        netw.append(l)
for l in netw + errors:
    print("LINT", l)
for l in libw:
    print("LIBRARY (not counted)", l)
for l in waived:
    print("WAIVED (unused internal signal)", l)
print(f"RESULT lint mode={'gate' if gate else 'rtl'} warnings={len(netw) + len(libw) + len(waived)} "
      f"netlist={len(netw)} library={len(libw)} waived={len(waived)} errors={len(errors)}")
sys.exit(1 if netw or errors else 0)
