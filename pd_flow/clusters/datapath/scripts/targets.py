#!/usr/bin/env python3
"""Explicit HPWL hinge targets (D10 cost item 4) for the placement-sensitive dp drivers of the reference
run, keyed by the driver's output NET (netlist-agnostic: drivers found by structure in the reference
netlist, never by instance name across netlists).

Classes of targeted nets (evidence: x0 baseline area classes and the x0 FIRM screens x_s0, xa_s1, xa_s2):
  removable  upsized dp drivers with fanout <= 7 whose net is short already (the resizer upsized them
             for wire, not for pin load): target = --frac x the shortest HPWL seen so far, floor --floor um;
  sensitive  dp-sink nets whose repair changed between screens (x0 vs FIRM): target = --frac-s x shortest;
  guard      high-fanout dp nets whose fanout buffers sat at the 0.2 pF cap limit: target = the seed HPWL
             (must not grow).
usage: targets.py --out JSON [--frac 0.5] [--frac-s 0.8] [--floor 12] [--placements DIR ...]"""
import sys, os, json, argparse
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import dplib

ap = argparse.ArgumentParser(); ap.add_argument('--out', required=True)
ap.add_argument('--frac', type=float, default=0.5); ap.add_argument('--frac-s', type=float, default=0.8)
ap.add_argument('--floor', type=float, default=12.0); ap.add_argument('--placements', nargs='*', default=[])
a = ap.parse_args()
d = dplib.Design(); dps = set(d.dp)
base = os.path.join(here, '..', 'baseline', ('h2_area_classes.json' if dplib.REF_TAG == 'h2' else dplib.REF_TAG + '_area_classes.json'))
A = json.load(open(base))
Ps = [dplib.seed_from_h2(d)] + [dplib.Placement.load(d, p) for p in a.placements]
Ws = [dplib.Wire(P) for P in Ps]


def onet(n):
    return [b for p, b in d.conns[n].items() if d.pdir(d.master[n], p) == 'output'][0]


def shortest(b):
    return min(W.net(b) for W in Ws)


out, why = {}, {}
for n, (m0, m1, da) in A['upsized'].items():
    if n not in dps: continue
    b = onet(n)
    if len(d.nets[b]) - 1 <= 7 and shortest(b) < 80:
        out[b] = round(max(a.floor, a.frac * shortest(b)), 1); why[b] = f'removable upsize {n} {m0}->{m1} +{da}'
# sensitive drivers whose sinks are dp (repair changed between x0 and the FIRM screens)
for q in ('config_chain[7]',):                       # flop Q net, non-dp driver with 15 dp sinks
    if q in d.nets:
        out[q] = round(a.frac_s * shortest(q), 1); why[q] = 'sensitive repair (flop Q net, dp sinks)'
for n in A['repair_by_driver']:
    if n not in dps: continue
    b = onet(n); fo = len(d.nets[b]) - 1
    if fo <= 20 and b not in out:
        out[b] = round(a.frac_s * shortest(b), 1); why[b] = f'repaired dp driver {n} fo {fo}'
    elif fo > 20:
        out[b] = round(Ws[0].net(b), 1); why[b] = f'guard (fanout-buffer cap) {n} fo {fo}'
json.dump({'reference': dplib.REF, 'netlist_sha16': d.nl_sha16, 'args': vars(a), 'targets': out, 'why': why},
          open(a.out, 'w'), indent=1)
for b in sorted(out, key=lambda b: why[b]): print(f'{b:24s} {out[b]:7.1f}  {why[b]}')
print(len(out), 'targets')
