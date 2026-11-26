#!/usr/bin/env python3
"""Partial-FIRM variant of a placement: only the dp cluster is FIRM (MACRO_PLACEMENT_CFG); every other
cell is placed by the tool (GPL with the dp cells as fixed obstacles, repair on GPL positions, DPL),
exactly as in the standard flow.  This is the mechanism a full harden with this cfg reproduces.
usage: make_partial.py <full_placement_dir> <out_dir> [--set b|struct]
  --set b      (default) dp = Architect B's in-context attribution (828 cells, h2 only)
  --set struct dp = attribute.py structural attribution of the reference netlist (netlist-agnostic)
The output keeps placement.json / macro_placement.cfg / manual_global_placements.json / reserve.json
restricted to the dp cells (so dryrun.py checks held and reservations for the dp cells only)."""
import sys, os, json, argparse, shutil
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import dplib
ap = argparse.ArgumentParser(); ap.add_argument('src'); ap.add_argument('out'); ap.add_argument('--set', default='b')
a = ap.parse_args()
d = dplib.Design()
if a.set == 'b':
    A = json.load(open(dplib.ATTR_JSON))['cells']
    keep = {n for n in d.custom if A[n]['label'] in dplib.DP_LABELS}
else:
    keep = set(d.dp)
P = json.load(open(os.path.join(a.src, 'placement.json')))
cells = {n: v for n, v in P['cells'].items() if n in keep}
meta = dict(P['meta']); meta.update({'partial_firm': True, 'partial_set': a.set, 'partial_from': os.path.abspath(a.src),
                                     'firm_cells': len(cells)})
os.makedirs(a.out, exist_ok=True)
json.dump({'meta': meta, 'cells': cells}, open(os.path.join(a.out, 'placement.json'), 'w'), indent=1)
with open(os.path.join(a.out, 'macro_placement.cfg'), 'w') as f:
    for n, p in cells.items():
        f.write(f"{n} {p['x']:.2f} {p['y']:.2f} {p['orient']}\n")
json.dump({n: {'location': [p['x'], p['y']], 'orientation': p['orient']} for n, p in cells.items()},
          open(os.path.join(a.out, 'manual_global_placements.json'), 'w'), indent=1)
json.dump({n: p['reserved_master'] for n, p in cells.items() if p.get('reserved_master')},
          open(os.path.join(a.out, 'reserve.json'), 'w'), indent=1, sort_keys=True)
print(f'{a.out}: {len(cells)} FIRM dp cells (set {a.set}) from {a.src}')
