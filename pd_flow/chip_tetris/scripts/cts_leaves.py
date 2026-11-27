#!/usr/bin/env python3
"""Clock-tree census of a CTS (or later) DEF: per leaf buffer the flop sinks, their CLK pin cap, the
dummy loads (clkload*) it drives, the leaf net HPWL (pin centres), and the CTS area by master.
usage: cts_leaves.py <def> [--json OUT] [-q]"""
import sys, os, json, argparse, collections
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import dplib
sys.path.insert(0, os.path.join(dplib.BDIR, 'tools'))
from def_nets import read_nets
from pdlib import read_def, liberty, lef_sizes


def census(path):
    L = liberty(); LEFS = lef_sizes(); N = read_nets(path); C = read_def(path)['comps']
    ctr = lambda i: (C[i]['x'] + LEFS[C[i]['master']][0] / 2, C[i]['y'] + LEFS[C[i]['master']][1] / 2)
    leaves = []; area = collections.Counter(); cnt = collections.Counter()
    for n, c in C.items():
        if n.startswith(('clkbuf_', 'clkload')):
            area[c['master']] += L[c['master']]['area']; cnt[c['master']] += 1
    for net, conns in N.items():
        drv = [i for i, p in conns if i.startswith('clkbuf_') and p == 'Z']
        if not drv: continue
        sinks = [(i, p) for i, p in conns if i != drv[0] and i != 'PIN']
        ff = [i for i, p in sinks if not i.startswith(('clkload', 'clkbuf_'))]
        if not ff: continue
        dm = [C[i]['master'] for i, p in sinks if i.startswith('clkload')]
        pts = [ctr(i) for i, _ in sinks] + [ctr(drv[0])]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        cap = sum(L[C[i]['master']]['pins'].get(p, {}).get('cap', 0) for i, p in sinks)
        ffcap = sum(L[C[i]['master']]['pins'].get(p, {}).get('cap', 0) for i, p in sinks if i in ff)
        leaves.append({'leaf': drv[0], 'ff': len(ff), 'ff_cap': round(ffcap, 5), 'cap_with_dummies': round(cap, 5), 'dummies': dm,
                       'hpwl': round(max(xs) - min(xs) + max(ys) - min(ys), 1),
                       'bbox': [round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)]})
    return {'def': path, 'leaves': sorted(leaves, key=lambda r: r['leaf']), 'n_leaves': len(leaves),
            'dummies': sum(len(r['dummies']) for r in leaves), 'dummy_area_total': round(sum(a for m, a in area.items()) - sum(
                area[m] for m in area if m.startswith('clkbuf')), 2),
            'cts_area': round(sum(area.values()), 3), 'masters': dict(cnt)}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('deff'); ap.add_argument('--json'); ap.add_argument('-q', action='store_true'); a = ap.parse_args()
    o = census(a.deff)
    print(f"leaves {o['n_leaves']} dummies {o['dummies']} cts {o['cts_area']} {o['masters']}")
    if not a.q:
        for r in o['leaves']:
            print(f"  {r['leaf']:20s} ff {r['ff']:3d} ffcap {r['ff_cap']:.4f} hpwl {r['hpwl']:6.1f} dummies {r['dummies']}")
    if a.json: json.dump(o, open(a.json, 'w'), indent=1)
