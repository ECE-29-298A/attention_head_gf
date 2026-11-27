#!/usr/bin/env python3
"""Clock-tree topology of a CTS DEF: per non-leaf buffer its children (leaf: flop count, dummies, centre),
and for leaves with fewer than --full flops the flop list with positions.
usage: cts_tree.py <def> [--full 20]"""
import sys, os, argparse
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import dplib, cts_leaves
sys.path.insert(0, os.path.join(dplib.BDIR, 'tools'))
from def_nets import read_nets
from pdlib import read_def
ap = argparse.ArgumentParser(); ap.add_argument('deff'); ap.add_argument('--full', type=int, default=20); a = ap.parse_args()
N = read_nets(a.deff); C = read_def(a.deff)['comps']; O = cts_leaves.census(a.deff); lv = {r['leaf']: r for r in O['leaves']}
for net, conns in sorted(N.items()):
    drv = [i for i, p in conns if i.startswith('clkbuf_') and p == 'Z']
    if not drv or drv[0] in lv: continue
    ch = [i for i, p in conns if i != drv[0] and i.startswith(('clkbuf_', 'clkload'))]
    print(drv[0], [(c, lv[c]['ff'], lv[c]['dummies'], [round((lv[c]['bbox'][0] + lv[c]['bbox'][2]) / 2), round((lv[c]['bbox'][1] + lv[c]['bbox'][3]) / 2)])
                   if c in lv else (c, C[c]['master']) for c in ch])
for net, conns in sorted(N.items()):
    drv = [i for i, p in conns if i in lv and p == 'Z']
    if not drv or lv[drv[0]]['ff'] >= a.full: continue
    ff = [(i, round(C[i]['x'], 1), round(C[i]['y'], 1)) for i, p in conns if i != drv[0] and not i.startswith('clkload')]
    print(drv[0], lv[drv[0]]['ff'], lv[drv[0]]['bbox'], ff)
