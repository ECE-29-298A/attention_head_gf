#!/usr/bin/env python3
"""Classify Verilator -Wall output for max_reg (SPEC.md R10).

Usage: check_lint.py <verilator stderr log> <dut file> [--gate]
RTL mode: passes only with no %Warning and no %Error (no waivers).
Gate mode (--gate): the DUT file is the netlist followed by the PDK cell models, separated
by the marker line written by gate/extract_cells.py. Warnings located after the marker are
in the unmodified PDK models (for example BLKSEQ, IMPLICIT, UNDRIVEN in the flop UDP
wrappers); they are counted and listed but do not fail, because the netlist under test
does not contain them. DECLFILENAME on the netlist module is a packaging artefact (the
models are in the same file) and is also not counted. Any other warning located in the
netlist, and any %Error, fails.
"""
import re
import sys

MARK = "// ==== end of netlist; PDK cell models follow ===="
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
        print("RESULT lint warnings=0 netlist=0 library=0 errors=1")
        sys.exit(1)
loc = re.compile(r"^%(Warning|Error)(-[A-Z_0-9]+)?: [^:]*:(\d+):")
netw, libw, errors = [], [], []
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
    else:
        netw.append(l)
for l in netw + errors:
    print("LINT", l)
for l in libw:
    print("LIBRARY (not counted)", l)
print(f"RESULT lint mode={'gate' if gate else 'rtl'} warnings={len(netw) + len(libw)} "
      f"netlist={len(netw)} library={len(libw)} errors={len(errors)}")
sys.exit(1 if netw or errors else 0)
