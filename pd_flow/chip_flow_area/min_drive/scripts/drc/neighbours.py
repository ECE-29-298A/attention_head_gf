#!/usr/bin/env python3
"""Orientation and abutting-neighbour census of one master in a placed DEF (mux2_1 DRC test coverage).
usage: neighbours.py <placed.def> [master, default mux2_1]"""
import re, sys, collections
txt = open(sys.argv[1]).read()
comp = txt.split("COMPONENTS")[1].split("END COMPONENTS")[0]
P = "gf180mcu_fd_sc_mcu7t5v0__"
cells = []
for m in re.finditer(r"-\s+(\S+)\s+(\S+)\s+(?:\+\s+SOURCE\s+\S+\s+)?\+\s+(?:PLACED|FIXED)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+(\S+)", comp):
    inst, master, x, y, o = m.groups()
    cells.append((inst, master.replace(P, ""), int(x), int(y), o))
target = sys.argv[2] if len(sys.argv) > 2 else "mux2_1"
mux = [c for c in cells if c[1] == target]
print(len(cells), "components;", target, len(mux), "orientations", dict(collections.Counter(c[4] for c in mux)))
lef = open("/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lef/gf180mcu_fd_sc_mcu7t5v0.lef").read()
units = int(re.search(r"UNITS DISTANCE MICRONS (\d+)", txt).group(1))
W = {m.group(1).replace(P, ""): round(float(m.group(2)) * units) for m in re.finditer(r"MACRO (\S+)\s.*?SIZE ([\d.]+) BY ([\d.]+)", lef, re.S)}
rows = collections.defaultdict(list)
for c in cells:
    rows[c[3]].append(c)
fam = collections.Counter(); pairs_or = collections.Counter()
for y, rc in rows.items():
    rc.sort(key=lambda c: c[2])
    for a, b in zip(rc, rc[1:]):
        if a[2] + W[a[1]] == b[2]:
            for me, other in ((a, b), (b, a)):
                if me[1] == target:
                    fam[re.sub(r"_\d+$", "", other[1])] += 1
                    pairs_or[(me[4], other[4])] += 1
print("abutting neighbour families:", dict(fam.most_common()))
print("orientation pairs (self, neighbour):", dict(pairs_or.most_common()))
