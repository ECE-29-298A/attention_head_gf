#!/usr/bin/env python3
"""Evaluate a floorplan spec against the real tile: region areas, taps/endcaps inside, expected cell
area (synthesized + h2 PnR reserve), packing at that area, overlaps, and an SVG from real coordinates.
usage: floorplan.py <spec.json> --attr ATTR.json --pnr PNR.json --ref-def REF.def --out-dir DIR"""
import sys, os, json, argparse, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdlib import read_def, lef_sizes, sha
ap = argparse.ArgumentParser(); ap.add_argument('spec'); ap.add_argument('--attr', required=True)
ap.add_argument('--pnr', required=True); ap.add_argument('--ref-def', required=True); ap.add_argument('--out-dir', required=True)
a = ap.parse_args()
S = json.load(open(a.spec)); R = read_def(a.ref_def); L = lef_sizes()
AT = json.load(open(a.attr)); PNR = json.load(open(a.pnr))
per = AT['per_label']
flops = {k: v['seq'] for k, v in per.items()}
tot_ff = sum(flops.values())
cts_total = 851.74   # h2 clock buffers + inverters (area/h2_classes.json 'cts')
EPS = 1e-6
def rect_area(r): return (r[2] - r[0]) * (r[3] - r[1])
def overlap(r, x0, y0, x1, y1): return max(0, min(r[2], x1) - max(r[0], x0)) * max(0, min(r[3], y1) - max(r[1], y0))
phys = [(n, c, L[c['master']]) for n, c in R['comps'].items() if n.startswith(('TAP_', 'PHY_EDGE'))]
res = {}; allrects = []
for name, reg in S['regions'].items():
    A = sum(rect_area(r) for r in reg['rects'])
    tap = sum(overlap(r, c['x'], c['y'], c['x'] + s[0], c['y'] + s[1]) for r in reg['rects'] for n, c, s in phys if n.startswith('TAP_'))
    endc = sum(overlap(r, c['x'], c['y'], c['x'] + s[0], c['y'] + s[1]) for r in reg['rects'] for n, c, s in phys if n.startswith('PHY_EDGE'))
    syn = sum(per[l]['area'] for l in reg['labels'] if l in per)
    ups = sum(PNR['upsize'].get(l, 0) for l in reg['labels']); rep = sum(PNR['repair'].get(l, 0) for l in reg['labels'])
    cts = cts_total * sum(flops.get(l, 0) for l in reg['labels']) / tot_ff
    exp_area = syn + ups + rep + cts
    res[name] = {'kind': reg['kind'], 'labels': reg['labels'], 'rects': reg['rects'], 'region_area': round(A, 1),
                 'tap_area': round(tap, 1), 'endcap_area': round(endc, 1), 'synth_area': round(syn, 1),
                 'reserve_upsize': round(ups, 1), 'reserve_repair': round(rep, 1), 'reserve_cts': round(cts, 1),
                 'expected_cell_area': round(exp_area, 1),
                 'packing_synth_only': round((syn + tap + endc) / A, 4),
                 'packing_expected': round((exp_area + tap + endc) / A, 4)}
    allrects += [(name, r) for r in reg['rects']]
errs = []
x_lo, x_hi = 4.48, 342.16; y_lo, y_hi = 3.92, 156.80
for i, (n1, r1) in enumerate(allrects):
    if r1[0] < x_lo - EPS or r1[2] > x_hi + EPS or r1[1] < y_lo - EPS or r1[3] > y_hi + EPS: errs.append(f'{n1} {r1} outside core')
    for v in (r1[1], r1[3]):
        if abs(((v - 3.92) / 3.92) - round((v - 3.92) / 3.92)) > 1e-6: errs.append(f'{n1} {r1} not row aligned')
    for v in (r1[0], r1[2]):
        if abs(((v - 3.36) / 0.56) - round((v - 3.36) / 0.56)) > 1e-6: errs.append(f'{n1} {r1} not site aligned')
    for n2, r2 in allrects[i + 1:]:
        if overlap(r1, *r2) > EPS: errs.append(f'{n1} {r1} overlaps {n2} {r2}')
core_place = (x_hi - x_lo) * (y_hi - y_lo)
used = sum(v['region_area'] for v in res.values())
tot = {'core_area': 51967.0, 'endcap_area': 342.45, 'placeable_area': round(core_place, 1), 'regions_area': round(used, 1),
       'unassigned_area': round(core_place - used, 1),
       'expected_stdcell_area': round(sum(v['expected_cell_area'] + v['tap_area'] + v['endcap_area'] for v in res.values()) + 342.45 - sum(v['endcap_area'] for v in res.values()), 1)}
out = {'spec': a.spec, 'spec_sha16': sha(a.spec), 'regions': res, 'totals': tot, 'errors': errs}
os.makedirs(a.out_dir, exist_ok=True)
json.dump(out, open(os.path.join(a.out_dir, 'floorplan_eval.json'), 'w'), indent=1)
for n, v in res.items():
    print(f"{n:5s} region {v['region_area']:8.1f}  synth {v['synth_area']:8.1f} + reserve {v['reserve_upsize'] + v['reserve_repair'] + v['reserve_cts']:6.1f} + taps {v['tap_area']:6.1f}  packing synth-only {v['packing_synth_only']:.1%}  expected {v['packing_expected']:.1%}")
print(tot); print('errors', errs)
# ---- SVG ----
SC = 4.0; W, H = R['die'][2] * SC, R['die'][3] * SC
def X(x): return x * SC
def Y(y): return H - y * SC
col = {'spi': '#d62728', 'ctrl': '#7f7f7f', 'div': '#9467bd', 'dp': '#1f77b4'}
sv = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W + 20:.0f}" height="{H + 130:.0f}" font-family="Helvetica,Arial,sans-serif">',
      f'<rect x="0" y="0" width="{W + 20:.0f}" height="{H + 130:.0f}" fill="#ffffff"/>', '<g transform="translate(10,10)">',
      f'<rect x="0" y="0" width="{W:.1f}" height="{H:.1f}" fill="#fafafa" stroke="#333" stroke-width="1"/>']
for r in R['rows']:
    sv.append(f'<rect x="{X(r["x"]):.1f}" y="{Y(r["y"] + 3.92):.1f}" width="{r["n"] * 0.56 * SC:.1f}" height="{3.92 * SC:.1f}" fill="none" stroke="#e3e3e3" stroke-width="0.5"/>')
for n, reg in S['regions'].items():
    for r in reg['rects']:
        sv.append(f'<rect x="{X(r[0]):.1f}" y="{Y(r[3]):.1f}" width="{(r[2] - r[0]) * SC:.1f}" height="{(r[3] - r[1]) * SC:.1f}" fill="{col.get(n, "#2ca02c")}" fill-opacity="0.28" stroke="{col.get(n, "#2ca02c")}" stroke-width="1.5"/>')
for n, rects in S.get('dp_subregions_soft', {}).items():
    for r in rects:
        sv.append(f'<rect x="{X(r[0]):.1f}" y="{Y(r[3]):.1f}" width="{(r[2] - r[0]) * SC:.1f}" height="{(r[3] - r[1]) * SC:.1f}" fill="none" stroke="#1f77b4" stroke-dasharray="4,3" stroke-width="1"/>')
    r = rects[0]; sv.append(f'<text x="{X(r[0]) + 4:.1f}" y="{Y(r[1]) - 4:.1f}" font-size="11" fill="#1f4f7f">{n} (soft)</text>')
for n, c, s in phys:
    sv.append(f'<rect x="{X(c["x"]):.1f}" y="{Y(c["y"] + s[1]):.1f}" width="{s[0] * SC:.1f}" height="{s[1] * SC:.1f}" fill="#444"/>')
for n, v in res.items():
    r = max(v['rects'], key=rect_area)
    sv.append(f'<text x="{X((r[0] + r[2]) / 2):.1f}" y="{Y((r[1] + r[3]) / 2):.1f}" font-size="14" font-weight="bold" text-anchor="middle" fill="#111">{n}</text>')
    sv.append(f'<text x="{X((r[0] + r[2]) / 2):.1f}" y="{Y((r[1] + r[3]) / 2) + 15:.1f}" font-size="11" text-anchor="middle" fill="#111">{v["region_area"]:.0f} um2, expected {v["packing_expected"]:.1%}</text>')
used_pins = {'clk', 'rst_n', 'ena', 'ui_in[0]', 'ui_in[1]', 'ui_in[2]', 'uo_out[0]', 'uo_out[1]', 'uio_in[1]', 'uio_in[2]', 'uio_in[4]', 'uio_in[5]', 'uio_out[0]', 'uio_out[1]', 'uio_out[3]', 'uio_oe[1]'}
for n, p in R['pins'].items():
    u = n in used_pins
    sv.append(f'<rect x="{X(p["x"]) - 2:.1f}" y="{Y(R["die"][3]):.1f}" width="4" height="7" fill="{"#d62728" if u else "#bbb"}"/>')
    if u: sv.append(f'<text x="{X(p["x"]):.1f}" y="{Y(R["die"][3]) + 18:.1f}" font-size="8" text-anchor="middle" fill="#a00">{n}</text>')
ly = H + 22
sv.append(f'<text x="0" y="{ly:.0f}" font-size="12" fill="#111">Floorplan B rev 1 on the real GF180 1x1 tile (die 346.64 x 160.72 um, 39 rows, taps and endcaps from the h2 DEF in dark grey, TT pins on the top edge; used pins red).</text>')
sv.append(f'<text x="0" y="{ly + 16:.0f}" font-size="12" fill="#111">Packing = (expected cells + taps inside) / region area; expected cells = in-context synthesized area + h2 PnR reserve (upsizing, repair buffers, CTS share).</text>')
sv.append(f'<text x="0" y="{ly + 32:.0f}" font-size="12" fill="#111">Unassigned placeable area {tot["unassigned_area"]:.0f} um2; dashed = soft sub-regions inside the datapath cluster.</text>')
sv.append('</g></svg>')
open(os.path.join(a.out_dir, 'floorplan_b.svg'), 'w').write('\n'.join(sv))
