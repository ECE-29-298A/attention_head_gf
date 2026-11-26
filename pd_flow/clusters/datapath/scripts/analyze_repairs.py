#!/usr/bin/env python3
"""Census of the nets the resizer repaired in a run: for each repaired driver (upsized, or its net
buffered), the net's fanout, sink labels, HPWL and bounding box at the given placement (synthesized
cells at their positions in `def`), total sink pin capacitance (tt Liberty), and the repair.
usage: analyze_repairs.py <area_classes.json> <def> [--json OUT]"""
import sys, os, json, argparse, collections
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import dplib
from dplib import read_def

ap = argparse.ArgumentParser(); ap.add_argument('classes'); ap.add_argument('deff'); ap.add_argument('--json')
a = ap.parse_args()
d = dplib.Design(); C = json.load(open(a.classes)); F = read_def(a.deff)
def pos(n):
    c = F['comps'].get(n)
    if c is None or c['x'] is None: return None
    return (c['x'] + d.LEFS[c['master']][0] / 2, c['y'] + 1.96)
drivers = set(C['upsized']) | set(C['repair_by_driver'])
out = {}
for n in sorted(drivers):
    if n not in d.master: continue
    outs = [b for p, b in d.conns[n].items() if d.pdir(d.master[n], p) == 'output']
    for b in outs:
        sinks = [(m, p) for m, p in d.nets[b] if (m, p) != (n, [q for q, bb in d.conns[n].items() if bb == b][0])]
        pts = [pos(m) for m, _ in sinks if pos(m)] + d.port_pts.get(b, [])
        pp = pos(n)
        if pp: pts.append(pp)
        xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
        cap = sum(d.LIB[d.master[m]]['pins'].get(p, {}).get('cap', 0) for m, p in sinks)
        out[n] = {'master_synth': d.master[n], 'master_final': F['comps'][n]['master'] if n in F['comps'] else None,
                  'label': d.label[n], 'net': d.netname.get(b, str(b)), 'fanout': len(sinks),
                  'ports': d.port_of_bit.get(b), 'sink_labels': dict(collections.Counter(d.label[m] for m, _ in sinks)),
                  'hpwl_um': round(max(xs) - min(xs) + max(ys) - min(ys), 1) if len(pts) > 1 else 0,
                  'bbox': [round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)] if pts else None,
                  'sink_cap_pf': round(cap, 4), 'repair': C['repair_by_driver'].get(n, []),
                  'upsize': C['upsized'].get(n)}
for n, v in out.items():
    print(f"{n:8s} {v['label']:20s} {v['master_synth']:9s}->{str(v['master_final']):9s} fo {v['fanout']:3d} hpwl {v['hpwl_um']:7.1f} "
          f"cap {v['sink_cap_pf']:.4f} {v['net'][:28]:28s} rep {[m for _, m in v['repair']]} sinks {v['sink_labels']}")
if a.json: json.dump(out, open(a.json, 'w'), indent=1)
