#!/usr/bin/env python3
"""flopnames.py <netlist.v> ... : instance name and master of every flop whose Q drives a net matching
--q REGEX (default core.mac.M[k] = max_reg's M, and core.mac.S[k] or core.score[k]). Prints JSON
{netlist: {qnet: [inst, master]}} so instance-name stability can be compared across runs."""
import json, re, sys
pat = re.compile(r'gf180mcu_fd_sc_mcu7t5v0__(s?dff\w*)\s+(\S+)\s*\((.*?)\);', re.S)
qre = re.compile(sys.argv[1]) if len(sys.argv) > 2 and sys.argv[1].startswith("re:") else None
args = sys.argv[1:]
rx = re.compile(r'core\.(mac\.M|exponent_unit\.D)\[\d+\]')
if args and args[0].startswith("re:"):
    rx = re.compile(args[0][3:]); args = args[1:]
out = {}
for fn in args:
    d = {}
    for m in pat.finditer(open(fn).read()):
        t, n, body = m.groups()
        q = re.search(r'\.Q\(\s*\\?(\S+?)\s*\)', body)
        if q and rx.search(q.group(1)):
            d[q.group(1)] = [n, t]
    out[fn] = dict(sorted(d.items(), key=lambda kv: (kv[0].split('[')[0], int(re.search(r'\[(\d+)\]', kv[0]).group(1)))))
print(json.dumps(out, indent=1))
