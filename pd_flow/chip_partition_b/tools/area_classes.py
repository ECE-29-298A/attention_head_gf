#!/usr/bin/env python3
"""Std-cell area of a finished LibreLane run, split by class, plus packing per region.
usage: area_classes.py <run_dir (…/runs/wokwi)> [--regions regions.json] [--json OUT]
Classes: synth (synthesized instances at their synthesized master), upsize (final - synthesized
master area of synthesized instances), tie (all tie cells, synthesized or recreated by
repair_tie_fanout), repair (load_slew*/fanout*/wire*/split*/rebuffer*/max_length*/...), cts
(clkbuf_*/clkload*), hold (hold*), antenna, tap, endcap, fill, other.  'stdcell' = all but fill,
which is what LibreLane reports as design__instance__area__stdcell.
regions.json: {"name": [x0, y0, x1, y1] (um), ...}; packing = non-fill cell area inside / area."""
import sys, os, re, json, glob, argparse, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdlib import liberty, lef_sizes, read_def, sha
ap = argparse.ArgumentParser(); ap.add_argument('run'); ap.add_argument('--regions'); ap.add_argument('--json')
ap.add_argument('--def', dest='deff'); ap.add_argument('--synth-nl')
a = ap.parse_args()
LIB = liberty(); LEFS = lef_sizes()
deff = a.deff or glob.glob(os.path.join(a.run, 'final', 'def', '*.def'))[0]
snl = a.synth_nl or glob.glob(os.path.join(a.run, '*-yosys-synthesis', '*.nl.v'))[0]
syn = {}
for m, inst in re.findall(r'^\s*gf180mcu_fd_sc_mcu7t5v0__(\w+)\s+(\S+)\s*\(', open(snl).read(), re.M):
    syn[inst.lstrip('\\')] = m
D = read_def(deff)
def area(m): return LIB[m]['area'] if m in LIB else LEFS[m][0] * LEFS[m][1]
def klass(n, m):
    if n in syn: return 'synth'
    if m.startswith('tie'): return 'tie'
    if n.startswith('FILLER') or m.startswith('fill'):
        return 'tap' if m.startswith('filltie') else 'fill'
    if n.startswith('TAP_') or m.startswith('filltie'): return 'tap'
    if n.startswith('PHY_EDGE') or m.startswith('endcap'): return 'endcap'
    if n.startswith('clkbuf_') or n.startswith('clkload') or n.startswith('cts'): return 'cts'
    if n.startswith('hold'): return 'hold'
    if n.startswith('ANTENNA') or m.startswith('antenna'): return 'antenna'
    if re.match(r'(load_slew|fanout|wire|split|rebuffer|max_length|max_cap|buffer|input|output)\d+', n): return 'repair'
    return 'other'
cls = collections.defaultdict(lambda: [0, 0.0]); upsized = 0; ups_area = 0.0; inst_cls = {}
for n, c in D['comps'].items():
    m = c['master']; k = klass(n, m); A = area(m)
    if k == 'synth':
        sm = syn[n]
        if sm.startswith('tie'): k = 'tie'
        else:
            A0 = area(sm); cls['synth'][0] += 1; cls['synth'][1] += A0
            if sm != m:
                upsized += 1; ups_area += A - A0
            inst_cls[n] = k; continue
    cls[k][0] += 1; cls[k][1] += A; inst_cls[n] = k
cls['upsize'] = [upsized, ups_area]
missing = [n for n in syn if n not in D['comps'] and not syn[n].startswith('tie')]
tot = {k: round(v[1], 3) for k, v in cls.items()}
stdcell = sum(v[1] for k, v in cls.items() if k != 'fill')
out = {'run': a.run, 'def': deff, 'def_sha16': sha(deff), 'synth_nl': snl, 'synth_nl_sha16': sha(snl),
       'classes': {k: {'count': v[0], 'area': round(v[1], 3)} for k, v in sorted(cls.items())},
       'stdcell': round(stdcell, 3), 'synth_instances_missing_in_def': missing}
mp = os.path.join(a.run, 'final', 'metrics.json')
if os.path.exists(mp):
    M = json.load(open(mp)); out['metrics_stdcell'] = M.get('design__instance__area__stdcell')
    out['metrics_core'] = M.get('design__core__area')
print(f"run {a.run}")
for k in ('synth', 'upsize', 'tie', 'repair', 'cts', 'hold', 'antenna', 'other', 'tap', 'endcap', 'fill'):
    if k in cls: print(f"  {k:8s} n={cls[k][0]:5d} area={cls[k][1]:10.2f}")
print(f"  stdcell (all but fill) {stdcell:.2f}   metrics.json {out.get('metrics_stdcell')}   missing synth {len(missing)}")
if a.regions:
    R = json.load(open(a.regions)); out['regions'] = {}
    dbu = 1.0
    for name, (x0, y0, x1, y1) in R.items():
        if name.startswith('_'): continue
        occ = collections.Counter()
        for n, c in D['comps'].items():
            if c['x'] is None or inst_cls.get(n) == 'fill': continue
            w, h = LEFS[c['master']]
            cx0, cy0 = c['x'], c['y']; cx1, cy1 = cx0 + w, cy0 + h   # bbox (orientation-independent for std cells)
            ox = max(0.0, min(cx1, x1) - max(cx0, x0)); oy = max(0.0, min(cy1, y1) - max(cy0, y0))
            if ox > 0 and oy > 0: occ[inst_cls.get(n, 'other')] += ox * oy
        ra = (x1 - x0) * (y1 - y0); used = sum(occ.values())
        out['regions'][name] = {'rect': [x0, y0, x1, y1], 'area': round(ra, 3), 'cell_area': round(used, 3),
                                'packing': round(used / ra, 4), 'by_class': {k: round(v, 2) for k, v in occ.items()}}
        print(f"  region {name:12s} {ra:9.1f} um2  cells {used:9.1f}  packing {used/ra:6.2%}  {dict((k, round(v)) for k, v in occ.items())}")
if a.json: json.dump(out, open(a.json, 'w'), indent=1)
