#!/usr/bin/env python3
"""check_held for a full LibreLane run with the M-FIRM + reservation mechanism (Architect A's check_held.py
contract, with B's reservations): for every step DEF from ManualMacroPlacement (17) to final, every custom cell
of <placement_dir>/placement.json is present, FIXED, at its configured origin, row and orientation; a cell whose
master changed (resizer in-place upsize) must lie inside its reserved span.  Also counts flow-added instances.
usage: check_held_run.py <placement_dir> <run_dir> <out.json>"""
import sys, os, json, glob, collections
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import dplib
from dplib import read_def

pdir, run, outp = sys.argv[1:4]
P = json.load(open(os.path.join(pdir, 'placement.json')))['cells']
D = dplib.Design()


def held(defpath):
    F = read_def(defpath); bad = collections.Counter(); ex = []; resized = {}
    for n, p in P.items():
        c = F['comps'].get(n); why = None
        if c is None: why = 'missing'
        elif c['status'] != 'FIXED': why = 'status ' + str(c['status'])
        elif c['orient'] != p['orient']: why = 'orient'
        elif abs(c['y'] - p['y']) > 1e-3: why = 'moved'
        else:
            w0 = D.LEFS[p['master']][0]; w1 = D.LEFS[c['master']][0]
            mir = p['orient'] in dplib.MIRRORED
            o0 = p['x'] + (w0 if mir else 0); o1 = c['x'] + (w1 if mir else 0)
            span0 = dplib.X0 + p['span_site'] * dplib.SITE; span1 = span0 + p['w_res_sites'] * dplib.SITE
            if abs(o0 - o1) > 1e-3: why = 'moved'
            elif c['master'] != p['master']:
                resized[n] = c['master']
                if c['x'] < span0 - 1e-3 or c['x'] + w1 > span1 + 1e-3: why = 'resized beyond reservation'
        if why:
            bad[why] += 1
            if len(ex) < 6: ex.append((n, why))
    added = sum(1 for n in F['comps'] if n not in P)
    return {'ok': not bad, 'violations': dict(bad), 'examples': ex, 'resized': len(resized), 'instances': len(F['comps']), 'not_in_cfg': added}


defs = []
for dd in sorted(glob.glob(os.path.join(run, '[0-9]*-*'))):
    k = int(os.path.basename(dd).split('-')[0])
    if k >= 17:
        defs += sorted(glob.glob(os.path.join(dd, '*.def')))
defs += glob.glob(os.path.join(run, 'final', 'def', '*.def'))
res = {os.path.relpath(p, run): held(p) for p in defs}
out = {'placement_dir': os.path.abspath(pdir), 'run': run, 'configured': len(P), 'defs_checked': len(res),
       'ALL_HELD': bool(res) and all(v['ok'] for v in res.values()), 'steps': res}
json.dump(out, open(outp, 'w'), indent=1)
print(f"check_held_run: {len(res)} DEFs, ALL_HELD {out['ALL_HELD']}, final resized {list(res.values())[-1]['resized'] if res else None}")
sys.exit(0 if out['ALL_HELD'] else 1)
