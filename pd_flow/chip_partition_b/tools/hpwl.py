#!/usr/bin/env python3
"""Total half-perimeter wirelength of every signal net (clock excluded), cell centres, pins at the
DEF pin locations.  Positions from a DEF and/or placement.json files (later sources win).
usage: hpwl.py <netlist.json> --def D.def [--placement P.json ...] [--labels-from ATTR.json]"""
import sys, os, json, argparse, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdlib import read_def, lef_sizes
ap = argparse.ArgumentParser(); ap.add_argument('netlist'); ap.add_argument('--def', dest='deff', required=True)
ap.add_argument('--placement', nargs='*', default=[]); ap.add_argument('--attr'); a = ap.parse_args()
L = lef_sizes(); D = read_def(a.deff)
TOP = json.load(open(a.netlist))['modules']['tt_um_attention_head_gf']
pos = {}
for n, c in D['comps'].items():
    if c['x'] is not None: pos[n] = (c['x'] + L[c['master']][0] / 2, c['y'] + 1.96)
for p in a.placement:
    for n, c in json.load(open(p))['cells'].items(): pos[n] = (c['x'] + c['w_sites'] * 0.28, c['y'] + 1.96)
clk = set(TOP['ports']['clk']['bits'])
pts = collections.defaultdict(list)
for pn, pd in TOP['ports'].items():
    for i, b in enumerate(pd['bits']):
        nm = pn if len(pd['bits']) == 1 else f'{pn}[{i}]'
        if nm in D['pins'] and isinstance(b, int): pts[b].append((D['pins'][nm]['x'], D['pins'][nm]['y']))
miss = set()
for n, c in TOP['cells'].items():
    for pin, bits in c['connections'].items():
        for b in bits:
            if isinstance(b, int) and b not in clk:
                if n in pos: pts[b].append(pos[n])
                else: miss.add(n)
lab = {n: v['label'] for n, v in json.load(open(a.attr))['cells'].items()} if a.attr else {}
tot = 0.0; by = collections.Counter()
for b, p in pts.items():
    if len(p) < 2: continue
    h = max(x for x, _ in p) - min(x for x, _ in p) + max(y for _, y in p) - min(y for _, y in p); tot += h
print(f"HPWL {tot:.1f} um over {sum(1 for p in pts.values() if len(p) >= 2)} nets; cells without position: {len(miss)}")
