#!/usr/bin/env python3
"""arcs.py <liberty> <cell> [...]: per timing arc (related_pin -> output) the cell_rise / cell_fall delay
at table index (slew i, load j) = (2, 2) and (3, 3), plus input pin capacitance. Used to assign the late,
glitch-prone chain input to the fastest pin (ripple_add review finding B1)."""
import re, sys
sys.path.insert(0, __import__("os").path.dirname(__file__))
from cellfun import _blocks
txt = open(sys.argv[1]).read()
def timing_groups(text):
    for m in re.finditer(r"\btiming\s*\(\s*\)\s*\{", text):
        i = m.end(); d = 1
        while d:
            d += {"{": 1, "}": -1}.get(text[i], 0); i += 1
        yield text[m.end():i - 1]
for cell in sys.argv[2:]:
    for name, body, s, e in _blocks(txt, "cell"):
        if name != "gf180mcu_fd_sc_mcu7t5v0__" + cell: continue
        for pn, pb, ps, pe in _blocks(body, "pin"):
            if 'direction : output' not in pb and 'direction : "output"' not in pb: continue
            for tb in timing_groups(pb):
                rp = re.search(r'related_pin\s*:\s*"(\w+)"', tb).group(1)
                ty = re.search(r'timing_type\s*:\s*"?(\w+)', tb)
                vals = {}
                for kind in ("cell_rise", "cell_fall", "rise_transition", "fall_transition"):
                    for kn, kb, ks, ke in _blocks(tb, kind) if kind in tb else []:
                        v = re.search(r'values\s*\((.*?)\)\s*;', kb, re.S).group(1)
                        rows = [[float(x) for x in r.strip().strip('"').split(",")] for r in re.findall(r'"[^"]*"', v)]
                        vals[kind] = (rows[2][2], rows[3][3])
                if vals:
                    print(f"{cell:10s} {rp:4s}->{pn:3s} {ty.group(1) if ty else '':16s} rise {vals.get('cell_rise')} fall {vals.get('cell_fall')}")
