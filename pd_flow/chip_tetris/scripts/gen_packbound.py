#!/usr/bin/env python3
"""Pure-Tetris packing bound for the dp cluster (method §4 "two placements"; D10 cost item 3).
Connectivity is ignored on purpose: the dp cells are packed by Hill's Tetris rule (cells in order of
their seed x; each goes to the row whose leftmost legal hole ending gives the smallest right edge),
starting at the region's left edge, into the sites left free by every other cell (other clusters at
their tool positions, taps, endcaps).  Reservations (upsizing spans) are kept.  The result is the
geometric bound on the cluster footprint and a deliberately hostile wiring test; it is screened with
the same dry run as the wire-aware candidates.
usage: gen_packbound.py --out DIR [--reserve R.json ...] [--movable union|struct|b] [--rows LO HI]"""
import sys, os, json, argparse, time, math
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import dplib, footprint
from dplib import NROWS, NSITES, legal_orients, MIRRORED

ap = argparse.ArgumentParser(); ap.add_argument('--out', required=True); ap.add_argument('--reserve', nargs='*', default=[])
ap.add_argument('--movable', default='union'); ap.add_argument('--rows', nargs=2, type=int)
a = ap.parse_args(); t0 = time.time()
d = dplib.Design(); P = dplib.seed_from_h2(d)
res = {}
for rp in a.reserve:
    for n, m in json.load(open(rp)).items():
        if n not in res or d.wsites(m) > d.wsites(res[n]): res[n] = m
need = {n: m for n, m in res.items() if n in P.cells and d.wsites(m) > P.cells[n]['wr']}
for n, m in res.items():
    if n in P.cells and d.wsites(m) <= P.cells[n]['wr'] and (P.cells[n].get('rm') is None or d.wsites(m) >= d.wsites(P.cells[n]['rm'])):
        P.cells[n]['rm'] = m
if need: dplib.reserve(P, need)
dp = sorted(footprint.members(d, a.movable))
f0 = footprint.footprint(d, P, dp)
occ = [[None] * NSITES for _ in range(NROWS)]
for r in range(NROWS):
    for k in d.blocked[r]: occ[r][k] = '#'
dps = set(dp)
for n, c in P.cells.items():
    if n in dps: continue
    for k in range(c['s'], c['s'] + c['wr']): occ[c['r']][k] = n
lo_r, hi_r = (a.rows if a.rows else (f0['row_range'][0], f0['row_range'][1]))
s_min = min(P.cells[n]['s'] for n in dp)
sites_needed = sum(P.cells[n]['wr'] for n in dp)
free_total = sum(1 for r in range(lo_r, hi_r + 1) for k in range(s_min, NSITES) if occ[r][k] is None)
def leftmost(r, w, start):
    row = occ[r]; k = start; run = 0
    while k < NSITES:
        if row[k] is None:
            run += 1
            if run == w: return k - w + 1
        else: run = 0
        k += 1
    return None
order = sorted(dp, key=lambda n: (P.def_xy(n)[0], P.cells[n]['r']))
ptr = {r: s_min for r in range(lo_r, hi_r + 1)}
for n in order:
    c = P.cells[n]; best = None
    for r in range(lo_r, hi_r + 1):
        s = leftmost(r, c['wr'], s_min)
        if s is None: continue
        key = (s + c['wr'], abs(r - c['r']))
        if best is None or key < best[0]: best = (key, r, s)
    if best is None: sys.exit(f'no room for {n}')
    _, r, s = best
    mir = c['o'] in MIRRORED
    c['r'], c['s'], c['o'] = r, s, legal_orients(r)[1 if mir else 0]
    for k in range(s, s + c['wr']): occ[r][k] = n
errs = P.check()
if errs: sys.exit('ERRORS ' + '; '.join(errs[:5]))
f1 = footprint.footprint(d, P, dp)
S0 = dplib.seed_from_h2(d)
nondp_moved = sorted(n for n in P.cells if n not in dps and (P.cells[n]['r'], P.def_xy(n)[0]) != (S0.cells[n]['r'], S0.def_xy(n)[0]))
W = dplib.Wire(P)
right = max(P.cells[n]['s'] + P.cells[n]['wr'] for n in dp)
meta = {'generator': 'gen_packbound.py', 'args': vars(a), 'hpwl_pins_um': round(W.total(), 1),
        'rows': [lo_r, hi_r], 'region_left_site': s_min, 'dp_span_sites': sites_needed,
        'area_floor_sites_per_row': math.ceil(sites_needed / (hi_r - lo_r + 1)),
        'free_sites_in_rows_from_left_edge': free_total, 'packed_right_site': right,
        'packed_width_um': round((right - s_min) * dplib.SITE, 2),
        'footprint_seed': f0, 'footprint_packed': f1, 'seconds': round(time.time() - t0, 1),
        'nondp_moved': nondp_moved, 'nondp_moved_reason': 'local legalization of the seed reservations (dplib.reserve)',
        'netlist_sha16': d.nl_sha16}
P.write(a.out, meta)
json.dump(meta, open(os.path.join(a.out, 'gen.json'), 'w'), indent=1)
print(f"{a.out}: {len(dp)} dp cells packed into rows {lo_r}-{hi_r} from site {s_min}; right edge site {right} "
      f"({meta['packed_width_um']} um wide); HPWL {W.total():.1f}; packing {f0['packing']} -> {f1['packing']}, "
      f"region {f0['region_um2']} -> {f1['region_um2']} um2")
