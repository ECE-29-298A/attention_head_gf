#!/usr/bin/env python3
"""D8 packing of the dp cluster region for a placement (and h2): the region is the union of row
segments [leftmost, rightmost dp span edge] in every row that holds a dp cell, on site boundaries;
packing = area of every placement-stage cell inside the region (dp, other clusters' synthesized
cells, ties, taps, endcaps; fill, and the flow's later repair/CTS cells, excluded) / region area.  Also: bounding box, rows, dp cell area, dp-only density.
usage: footprint.py <placement_dir|h2> [...] [--set b|struct|union]"""
import sys, os, json, collections, argparse
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import dplib
from dplib import SITE, ROWH, X0, Y0, row_of, site_of


def members(d, which):
    if which == 'all':                 # whole chip: every synthesized non-tie cell
        return set(d.custom)
    if dplib.REF_TAG != 'h2':          # Architect B's attribution exists for h2 only: structural elsewhere
        return set(d.dp)
    A = json.load(open(dplib.ATTR_JSON))['cells'] if which in ('b', 'union') else {}
    b = {n for n in d.custom if A.get(n, {}).get('label') in dplib.DP_LABELS}
    return b if which == 'b' else (set(d.dp) if which == 'struct' else b | set(d.dp))


def footprint(d, P, dp):
    occ = {}                                       # (row, site) -> cell
    for n, c in P.cells.items():
        w = d.wsites(c['m']); cs = c['s'] + (c['wr'] - w if c['o'] in dplib.MIRRORED else 0)
        for k in range(cs, cs + w): occ[(c['r'], k)] = n
    for n, c in d.h2.items():                     # placement-stage cells not in P: ties, taps, endcaps (seed DEF)
        if n in P.cells or c['x'] is None: continue
        if not (n.startswith(('TAP_', 'PHY_EDGE')) or c['master'].startswith('tie')): continue
        m = c['master']
        if m not in d.LEFS: continue
        r, s = row_of(c['y']), site_of(c['x'])
        for k in range(s, s + d.wsites(m)): occ[(r, k)] = n
    seg = {}
    for n in dp:
        c = P.cells[n]; w = d.wsites(c['m']); cs = c['s'] + (c['wr'] - w if c['o'] in dplib.MIRRORED else 0)
        lo, hi = seg.get(c['r'], (10 ** 9, -1)); seg[c['r']] = (min(lo, cs), max(hi, cs + w))
    sites = sum(hi - lo for lo, hi in seg.values())
    used = sum(1 for r, (lo, hi) in seg.items() for k in range(lo, hi) if (r, k) in occ)
    dpsites = sum(d.wsites(P.cells[n]['m']) for n in dp)
    xs = [X0 + lo * SITE for lo, _ in seg.values()] + [X0 + hi * SITE for _, hi in seg.values()]
    return {'rows': len(seg), 'row_range': [min(seg), max(seg)], 'region_um2': round(sites * SITE * ROWH, 1),
            'packing': round(used / sites, 4), 'dp_only_density': round(dpsites / sites, 4),
            'bbox_um': [round(min(xs), 2), round(Y0 + min(seg) * ROWH, 2), round(max(xs), 2), round(Y0 + (max(seg) + 1) * ROWH, 2)],
            'dp_cells': len(dp), 'dp_area_um2': round(sum(d.area(P.cells[n]['m']) for n in dp), 1)}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('pdirs', nargs='+'); ap.add_argument('--set', default='union'); ap.add_argument('--json')
    a = ap.parse_args(); d = dplib.Design(); dp = members(d, a.set); out = {}
    for p in a.pdirs:
        P = dplib.seed_from_h2(d) if p == 'h2' else dplib.Placement.load(d, p)
        f = footprint(d, P, [n for n in dp if n in P.cells]); out[p] = f
        print(f"{os.path.basename(p.rstrip('/')):12s} rows {f['rows']} {f['row_range']} region {f['region_um2']:8.1f} um2  packing {f['packing']:.3f}  "
              f"dp-only {f['dp_only_density']:.3f}  bbox {f['bbox_um']}")
    if a.json: json.dump(out, open(a.json, 'w'), indent=1)
