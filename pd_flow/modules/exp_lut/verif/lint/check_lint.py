#!/usr/bin/env python3
"""Classify Verilator -Wall output for exp_lut (SPEC.md R15).

Usage: check_lint.py <verilator stderr log> <dut file> [--gate] [--registered N]
RTL mode: passes only with no %Warning and no %Error (no waivers).
Gate mode (--gate): the DUT file is the netlist followed by the PDK cell models, separated
by the marker line written by gate/extract_cells.py. Warnings located after the marker are
in the unmodified PDK models (BLKSEQ, IMPLICIT, UNDRIVEN in the flop UDP wrappers); they are
listed but not counted, because the netlist under test does not contain them.
DECLFILENAME on the netlist module is a packaging artefact (the models are in the same
file) and is also not counted. One port waiver, gate mode with --registered 0 only:
UNUSEDSIGNAL on exactly the input ports `clk` and `rst_n`. A REGISTERED = 0 netlist has no
state, so these required ports (R13) are unconnected inside it; the RTL suppresses the same
warning with its `_unused` wire, which synthesis removes. Any other warning located in the
netlist, and any %Error, fails.
"""
import re
import sys

MARK = "// ==== end of netlist; PDK cell models follow ===="
log, dut = sys.argv[1], sys.argv[2]
gate = "--gate" in sys.argv[3:]
reg = None
if "--registered" in sys.argv:
    reg = int(sys.argv[sys.argv.index("--registered") + 1])
text = open(log).read()
mark = None
if gate:
    for i, l in enumerate(open(dut), 1):
        if l.rstrip() == MARK:
            mark = i
            break
    if mark is None:
        print("LINT gate mode but no end-of-netlist marker in the DUT file")
        print("RESULT lint warnings=0 netlist=0 library=0 port_waived=0 errors=1")
        sys.exit(1)
loc = re.compile(r"^%(Warning|Error)(-[A-Z_0-9]+)?: [^:]*:(\d+):")
portw = re.compile(r"^%Warning-UNUSEDSIGNAL: [^:]*:\d+:\d+: Signal is not used: '(clk|rst_n)'$")
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
    if gate and line > mark:
        libw.append(l)
    elif gate and l.startswith("%Warning-DECLFILENAME"):
        libw.append(l)
    elif gate and reg == 0 and portw.match(l.strip()):
        waived.append(l)
    else:
        netw.append(l)
for l in netw + errors:
    print("LINT", l)
for l in libw:
    print("LIBRARY (not counted)", l)
for l in waived:
    print("PORT WAIVER (REGISTERED=0 netlist, unused clk/rst_n)", l)
print(f"RESULT lint mode={'gate' if gate else 'rtl'} warnings={len(netw) + len(libw) + len(waived)} "
      f"netlist={len(netw)} library={len(libw)} port_waived={len(waived)} errors={len(errors)}")
sys.exit(1 if netw or errors else 0)
