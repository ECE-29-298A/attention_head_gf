#!/usr/bin/env python3
"""Classify Verilator -Wall output for ripple_add (SPEC.md R8).

Usage: check_lint.py <verilator stderr log> <N>
Passes if there are no %Error lines and every %Warning is the single documented waiver:
UNUSEDSIGNAL on bit N of the internal carry vector c (the dropped carry out). Any other
warning, or that warning on any other signal or bit, fails.
"""
import re
import sys

text = open(sys.argv[1]).read()
n = int(sys.argv[2])
waiver = re.compile(r"^%Warning-UNUSEDSIGNAL: .*Bits of signal are not used: 'c'\[" + str(n) + r"\]$")
warnings = [l for l in text.splitlines() if l.startswith("%Warning")]
errors = [l for l in text.splitlines() if l.startswith("%Error") and "Exiting due to" not in l]
waived = [l for l in warnings if waiver.match(l)]
other = [l for l in warnings if not waiver.match(l)]
for l in other + errors:
    print("LINT", l)
print(f"RESULT lint N={n} warnings={len(warnings)} waived={len(waived)} other={len(other)} errors={len(errors)}")
sys.exit(1 if other or errors else 0)
