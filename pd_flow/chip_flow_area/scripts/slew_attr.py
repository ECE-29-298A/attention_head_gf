#!/usr/bin/env python3
"""Attribute max-slew violators in a LibreLane checks.rpt to their driving net and driver master.

usage: slew_attr.py <checks.rpt> <final.nl.v>
"""
import re
import sys
from collections import Counter, defaultdict

rpt, nl = sys.argv[1], sys.argv[2]
txt = open(rpt).read()
sec = txt.split("max slew", 1)[1].split("max fanout", 1)[0]
pins = re.findall(r"^(\S+)/(\S+)\s+[\d.]+\s+([\d.]+)\s+-[\d.]+ \(VIOLATED\)", sec, re.M)

# instance -> master, pin->net, net -> drivers
inst_re = re.compile(r"^\s*gf180mcu_fd_sc_mcu7t5v0__(\S+)\s+(\\?\S+)\s*\((.*?)\);", re.M | re.S)
conn_re = re.compile(r"\.(\w+)\(\s*(\\?[^()]*?)\s*\)")
OUT = {"Z", "ZN", "Q", "CO", "S", "ZN"}
master, pinnet, drv = {}, {}, {}
for m in inst_re.finditer(open(nl).read()):
    mst, inst, body = m.group(1), m.group(2).lstrip("\\"), m.group(3)
    master[inst] = mst
    for p, n in conn_re.findall(body):
        n = n.strip().lstrip("\\").strip()
        pinnet[(inst, p)] = n
        if p in OUT:
            drv[n] = (inst, mst)
by_net = Counter()
worst = defaultdict(float)
for inst, p, slew in pins:
    inst = inst.lstrip("\\")
    n = pinnet.get((inst, p))
    if n is None and p in OUT:
        n = "?"
    by_net[n] += 1
    worst[n] = max(worst[n], float(slew))
print(f"{len(pins)} violating pins on {len(by_net)} nets")
for n, c in by_net.most_common():
    d = drv.get(n, ("port/unknown", "-"))
    print(f"  {c:4d}  worst {worst[n]:6.3f} ns  net {n:30s} driver {d[0]} ({d[1]})")
