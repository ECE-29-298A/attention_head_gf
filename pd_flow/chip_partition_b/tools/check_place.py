#!/usr/bin/env python3
"""Independent validator for a region placement (placement.json from region_place.py or any
generator using the same format).
usage: check_place.py <placement.json> --netlist N.json --attr ATTR.json --ref-def REF.def
                      [--final-def FINAL.def] [--json OUT]
Pre-flow checks (exit 1 on any failure): every cell of the labels present once with its netlist
master; x on the site grid; y on a row; orientation = row orientation; inside the region; no
overlap between placed cells, taps or endcaps; packing recomputed from Liberty areas.
--final-def: post-flow report (no pass/fail on drift): status, displacement from the intended
location, master changes (upsizing), mirroring, and region packing of all non-fill cells."""
import sys, os, json, argparse, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdlib import lef_sizes, read_def, liberty, sha
ap = argparse.ArgumentParser(); ap.add_argument('placement'); ap.add_argument('--netlist', required=True)
ap.add_argument('--attr', required=True); ap.add_argument('--ref-def', required=True)
ap.add_argument('--final-def'); ap.add_argument('--json')
a = ap.parse_args()
P = json.load(open(a.placement)); meta, pl = P['meta'], P['cells']
LEFS = lef_sizes(); LIB = liberty(); R = read_def(a.ref_def)
TOP = json.load(open(a.netlist))['modules']['tt_um_attention_head_gf']
ATTR = json.load(open(a.attr))['cells']
SITE, ROWH, EPS = 0.56, 3.92, 1e-6
x0r = R['rows'][0]['x']; rowor = {round(r['y'], 3): r['orient'] for r in R['rows']}
errs = []
want = {n for n, c in TOP['cells'].items() if ATTR.get(n, {}).get('label') in meta['labels'] and not c['type'].split('__')[1].startswith('tie')}
if set(pl) != want: errs.append(f'cell set mismatch: missing {sorted(want - set(pl))[:5]} extra {sorted(set(pl) - want)[:5]}')
RECTS = meta.get('rects') or [meta['region']]
def inside(x, y, w): return any(x >= r[0] - EPS and x + w <= r[2] + EPS and y >= r[1] - EPS and y + ROWH <= r[3] + EPS for r in RECTS)
def ov_area(x, y, w, h): return sum(max(0, min(x + w, r[2]) - max(x, r[0])) * max(0, min(y + h, r[3]) - max(y, r[1])) for r in RECTS)
rects = []
for n, p in pl.items():
    m = TOP['cells'][n]['type'].split('__')[1] if n in TOP['cells'] else None
    if m != p['master']: errs.append(f'{n}: master {p["master"]} != netlist {m}')
    w = LEFS[p['master']][0]
    if abs(((p['x'] - x0r) / SITE) - round((p['x'] - x0r) / SITE)) > 1e-6: errs.append(f'{n}: x {p["x"]} off site grid')
    y = round(p['y'], 3)
    if y not in rowor: errs.append(f'{n}: y {p["y"]} not on a row')
    elif p['orient'] not in ({'N', 'FN'} if rowor[y] == 'N' else {'FS', 'S'}): errs.append(f'{n}: orient {p["orient"]} vs row {rowor[y]}')
    if not inside(p['x'], p['y'], max(w, p.get('w_res_sites', 0) * SITE)): errs.append(f'{n}: outside region')
    wr = max(w, p.get('w_res_sites', 0) * SITE)
    rects.append((y, p['x'], p['x'] + wr, n))
for n, c in R['comps'].items():
    if n.startswith(('TAP_', 'PHY_EDGE')): rects.append((round(c['y'], 3), c['x'], c['x'] + LEFS[c['master']][0], n))
byrow = collections.defaultdict(list)
for r in rects: byrow[r[0]].append(r)
ov = 0
for y, lst in byrow.items():
    lst.sort(key=lambda r: (r[1], r[2]))
    end, who = -1e9, None
    for r in lst:                       # sweep: overlap with any earlier rect still open
        if r[1] < end - EPS:
            ov += 1
            if ov <= 10: errs.append(f'overlap {who} / {r[3]} at y {y}')
        if r[2] > end: end, who = r[2], r[3]
cell_area = sum(LIB[p['master']]['area'] for p in pl.values())
tap_area = 0.0
for n, c in R['comps'].items():
    if n.startswith('TAP_'):
        tap_area += ov_area(c['x'], c['y'], LEFS[c['master']][0], ROWH)
ra = sum((r[2] - r[0]) * (r[3] - r[1]) for r in RECTS)
out = {'placement': a.placement, 'placement_sha16': sha(a.placement), 'cells': len(pl), 'errors': errs,
       'overlaps': ov, 'rects': RECTS, 'region_area': round(ra, 3), 'cell_area': round(cell_area, 3),
       'tap_area': round(tap_area, 3), 'packing_incl_taps': round((cell_area + tap_area) / ra, 4)}
print(f"pre-flow: {len(pl)} cells, {len(errs)} errors, packing {(cell_area + tap_area) / ra:.2%} "
      f"(cells {cell_area:.1f} + taps {tap_area:.1f} over {ra:.1f} um2)")
for e in errs[:12]: print('  ERROR', e)
if a.final_def:
    F = read_def(a.final_def); disp, st, ups, mir, miss = [], collections.Counter(), [], 0, []
    for n, p in pl.items():
        c = F['comps'].get(n)
        if not c: miss.append(n); continue
        st[c['status']] += 1
        d = abs(c['x'] - p['x']) + abs(c['y'] - p['y']); disp.append((d, n))
        if c['master'] != p['master']:
            fits = LEFS[c['master']][0] <= max(LEFS[p['master']][0], p.get('w_res_sites', 0) * SITE) + 1e-6
            ups.append((n, p['master'], c['master'], 'within reservation' if fits else 'EXCEEDS reservation'))
        if c['orient'] != p['orient']: mir += 1
    disp.sort(reverse=True)
    occ = collections.Counter()
    for n, c in F['comps'].items():
        if c['x'] is None or n.startswith('FILLER') or c['master'].startswith(('fill_', 'fillcap', 'decap')): continue
        o = ov_area(c['x'], c['y'], LEFS[c['master']][0], ROWH)
        if o > 0:
            k = 'custom' if n in pl else ('tap' if n.startswith('TAP_') else ('other_synth' if n in TOP['cells'] else 'inserted'))
            occ[k] += o
    moved = [x for x in disp if x[0] > 1e-6]
    out['final'] = {'def': a.final_def, 'def_sha16': sha(a.final_def), 'missing': miss, 'status': dict(st),
                    'moved': len(moved), 'max_disp_um': round(disp[0][0], 3) if disp else 0,
                    'mean_disp_um': round(sum(d for d, _ in disp) / max(1, len(disp)), 3),
                    'top_moves': [(n, round(d, 2)) for d, n in disp[:8]], 'master_changes': ups,
                    'orient_changes': mir, 'region_occupancy_um2': {k: round(v, 2) for k, v in occ.items()},
                    'region_packing_final': round(sum(occ.values()) / ra, 4)}
    f = out['final']
    print(f"post-flow: status {f['status']}, moved {f['moved']}/{len(pl)}, max disp {f['max_disp_um']} um, mean {f['mean_disp_um']} um, "
          f"masters changed {len(ups)}, orient changed {mir}, region packing {f['region_packing_final']:.2%} {f['region_occupancy_um2']}")
if a.json: json.dump(out, open(a.json, 'w'), indent=1)
sys.exit(1 if errs else 0)
