#!/usr/bin/env python3
"""Attribute PnR-inserted area of a finished run to RTL modules.
usage: repair_attrib.py <run_dir> <attribution.json> [--json OUT]
upsized instance -> its own label; repair buffer -> label of the original (non-buffer) driver of
the net it buffers; CTS sinks per label; hold buffers -> label of the sink they feed."""
import sys, os, json, glob, argparse, collections, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdlib import liberty, read_def
from def_nets import read_nets
ap = argparse.ArgumentParser(); ap.add_argument('run'); ap.add_argument('attr'); ap.add_argument('--json')
a = ap.parse_args()
LIB = liberty()
deff = glob.glob(os.path.join(a.run, 'final', 'def', '*.def'))[0]
snl = glob.glob(os.path.join(a.run, '*-yosys-synthesis', '*.nl.v'))[0]
syn = {i.lstrip('\\'): m for m, i in re.findall(r'^\s*gf180mcu_fd_sc_mcu7t5v0__(\w+)\s+(\S+)\s*\(', open(snl).read(), re.M)}
D = read_def(deff); N = read_nets(deff)
lab = {n: v['label'] for n, v in json.load(open(a.attr))['cells'].items()}
drv, ins = {}, collections.defaultdict(dict)
for net, conns in N.items():
    for i, p in conns:
        if i == 'PIN': continue
        m = D['comps'][i]['master']; d = LIB[m]['pins'].get(p, {}).get('dir')
        if d == 'output': drv[net] = i
        elif d == 'input': ins[i][p] = net
    if not any(i != 'PIN' and LIB[D['comps'][i]['master']]['pins'].get(p, {}).get('dir') == 'output' for i, p in conns):
        drv.setdefault(net, 'PORT')
def isrep(n): return re.match(r'(load_slew|fanout|wire|split|rebuffer|max_length)\d+', n) is not None
def origin(i, depth=0):
    if not isrep(i) or depth > 20: return i
    net = next(iter(ins[i].values())); return origin(drv.get(net, '?'), depth + 1)
res = collections.defaultdict(lambda: collections.Counter())
for n, c in D['comps'].items():
    m = c['master']
    if n in syn and syn[n] != m and not syn[n].startswith('tie'):
        res['upsize'][lab.get(n, '?')] += LIB[m]['area'] - LIB[syn[n]]['area']
    elif isrep(n):
        o = origin(n); res['repair'][lab.get(o, o if o == 'PORT' else '?')] += LIB[m]['area']
    elif n.startswith('hold'):
        net = next(n2 for n2, cs in N.items() if (n, 'Z') in cs)
        sinks = [i for i, p in N[net] if i != n]
        res['hold'][lab.get(sinks[0], '?') if sinks else '?'] += LIB[m]['area']
out = {k: {l: round(v, 2) for l, v in sorted(c.items(), key=lambda x: -x[1])} for k, c in res.items()}
for k, c in out.items(): print(k, round(sum(c.values()), 2), c)
if a.json: json.dump(out, open(a.json, 'w'), indent=1)
