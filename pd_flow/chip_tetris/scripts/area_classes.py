#!/usr/bin/env python3
"""Std-cell area of a placed/routed DEF by class, against the h2 synthesized netlist, plus the
repaired-driver census.
usage: area_classes.py <def> [--json OUT]
Classes: synth (synthesized instances at their synthesized master), upsize (final - synthesized
master area; synthesized netlist = the reference run's, dplib.REF / env DP_REF), tie, repair (load_slew/fanout/wire/split/rebuffer/max_length buffers), cts
(clkbuf_*/clkload*), hold (hold*), antenna, tap, endcap, fill, other.  stdcell = all but fill.
Repaired drivers: synthesized instances that were upsized, and original drivers (through buffer
chains) of nets that received repair buffers.  The dp flag uses the structural attribution
(attribute.py) of the reference netlist."""
import sys, os, re, json, argparse, collections
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import dplib
from dplib import read_def, sha, liberty, lef_sizes
sys.path.insert(0, os.path.join(dplib.BDIR, 'tools'))
from def_nets import read_nets

REP = re.compile(r'(load_slew|fanout|wire|split|rebuffer|max_length|max_cap)\d+')


def classify(defpath):
    LIB = liberty(); LEFS = lef_sizes()
    import attribute
    C = attribute.parse_nl(dplib.REF_SYN_NL)
    syn = {n: m for n, (m, _) in C.items()}
    lab, _ = attribute.attribute(C, lambda m, p: LIB[m]['pins'].get(p, {}).get('dir'))
    D = read_def(defpath)
    area = lambda m: LIB[m]['area'] if m in LIB else LEFS[m][0] * LEFS[m][1]
    cls = collections.defaultdict(lambda: [0, 0.0]); ups = {}
    kinds = {}
    for n, c in D['comps'].items():
        m = c['master']
        if n in syn and not syn[n].startswith('tie'):
            cls['synth'][0] += 1; cls['synth'][1] += area(syn[n])
            if syn[n] != m:
                ups[n] = (syn[n], m, round(area(m) - area(syn[n]), 3))
            kinds[n] = 'synth'; continue
        if m.startswith('tie'): k = 'tie'
        elif m.startswith('filltie') or n.startswith('TAP_'): k = 'tap'
        elif m.startswith('endcap') or n.startswith('PHY_EDGE'): k = 'endcap'
        elif m.startswith(('fill', 'decap')) or n.startswith('FILLER'): k = 'fill'
        elif n.startswith(('clkbuf_', 'clkload', 'cts')): k = 'cts'
        elif n.startswith('hold'): k = 'hold'
        elif n.startswith('ANTENNA') or m.startswith('antenna'): k = 'antenna'
        elif REP.match(n): k = 'repair'
        else: k = 'other'
        cls[k][0] += 1; cls[k][1] += area(m); kinds[n] = k
    cls['upsize'] = [len(ups), sum(v[2] for v in ups.values())]
    stdcell = sum(v[1] for k, v in cls.items() if k != 'fill')
    # repaired drivers: follow each repair buffer's input net back to a non-repair driver
    N = read_nets(defpath)
    drv, inp = {}, collections.defaultdict(dict)
    for net, conns in N.items():
        for i, p in conns:
            if i == 'PIN' or i not in D['comps']:
                continue
            m = D['comps'][i]['master']; dr = LIB.get(m, {}).get('pins', {}).get(p, {}).get('dir')
            if dr == 'output': drv[net] = (i, p)
            elif dr == 'input': inp[i][p] = net
    def origin(i, depth=0):
        if not REP.match(i) or depth > 30: return i
        net = next(iter(inp[i].values()), None)
        return origin(drv.get(net, ('PORT', ''))[0], depth + 1) if net else i
    rep_by_drv = collections.defaultdict(list)
    for n, k in kinds.items():
        if k == 'repair':
            rep_by_drv[origin(n)].append((n, D['comps'][n]['master']))
    drivers = set(ups) | set(rep_by_drv)
    dp = {'dp'}
    out = {'def': defpath, 'def_sha16': sha(defpath), 'netlist': dplib.REF_SYN_NL, 'dp_attribution': 'structural (attribute.py)',
           'classes': {k: {'count': v[0], 'area': round(v[1], 3)} for k, v in sorted(cls.items())},
           'stdcell': round(stdcell, 3),
           'upsized': {n: list(v) for n, v in sorted(ups.items())},
           'repair_by_driver': {k: v for k, v in sorted(rep_by_drv.items())},
           'repaired_drivers': len(drivers),
           'repaired_drivers_dp': sum(1 for n in drivers if lab.get(n) in dp),
           'upsize_area_dp': round(sum(v[2] for n, v in ups.items() if lab.get(n) in dp), 3),
           'repair_area_dp': round(sum(area(m) for o, lst in rep_by_drv.items() if lab.get(o) in dp for _, m in lst), 3),
           'cts_masters': dict(collections.Counter(D['comps'][n]['master'] for n, k in kinds.items() if k == 'cts')),
           'synth_missing': [n for n in syn if n not in D['comps'] and not syn[n].startswith('tie')]}
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('deff'); ap.add_argument('--json'); a = ap.parse_args()
    o = classify(a.deff)
    for k in ('synth', 'upsize', 'tie', 'repair', 'cts', 'hold', 'antenna', 'other', 'tap', 'endcap', 'fill'):
        if k in o['classes']:
            print(f"  {k:8s} n={o['classes'][k]['count']:5d} area={o['classes'][k]['area']:10.2f}")
    print(f"  stdcell {o['stdcell']:.2f}  repaired drivers {o['repaired_drivers']} (dp {o['repaired_drivers_dp']})  "
          f"dp upsize {o['upsize_area_dp']} dp repair {o['repair_area_dp']}  cts {o['cts_masters']}")
    if a.json:
        json.dump(o, open(a.json, 'w'), indent=1)
