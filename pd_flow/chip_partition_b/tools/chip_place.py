#!/usr/bin/env python3
"""Whole-chip custom placement from a floorplan spec: every non-tie synthesized cell is placed by
region_place.py inside its cluster's region; regions are placed in turn for several passes, each
seeing the current positions of the other regions' cells as anchors (unplaced cells sit at their
region's centroid).  Keeps already-placed regions given with --fixed REGION=DIR untouched.
usage: chip_place.py --spec SPEC.json --out DIR [--fixed spi=placements/spi_p1] [--passes 2]
                     [--iters dp=400000,ctrl=150000,div=150000] [--reserve RES.json] [--seed 1]"""
import sys, os, json, argparse, subprocess, collections
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
from pdlib import sha, read_def, lef_sizes
ap = argparse.ArgumentParser(); ap.add_argument('--spec', required=True); ap.add_argument('--out', required=True)
ap.add_argument('--fixed', nargs='*', default=[]); ap.add_argument('--passes', type=int, default=2)
ap.add_argument('--iters', default='dp=400000,ctrl=150000,div=150000'); ap.add_argument('--reserve'); ap.add_argument('--seed', type=int, default=1)
ap.add_argument('--keep-rows', action='store_true')
ap.add_argument('--seed-from', help='previous chip_place output dir: seed every region from its <region>_prev.def')
ap.add_argument('--netlist', default=os.path.join(here, '..', 'connectivity', 'h2_vnames.json'))
ap.add_argument('--attr', default=os.path.join(here, '..', 'connectivity', 'h2_attribution.json'))
ap.add_argument('--ref-def', default='/Users/samuelzhang/ttharden/fx_h2_k6/runs/wokwi/final/def/tt_um_attention_head_gf.def')
ap.add_argument('--init-def', default='/Users/samuelzhang/ttharden/fx_h2_k6/runs/wokwi/28-openroad-globalplacement/tt_um_attention_head_gf.def')
a = ap.parse_args()
S = json.load(open(a.spec))['regions']; ATTR = json.load(open(a.attr))['cells']
iters = dict(kv.split('=') for kv in a.iters.split(','))
fixed = dict(f.split('=') for f in a.fixed)
os.makedirs(a.out, exist_ok=True)
lab2reg = {l: r for r, v in S.items() for l in v['labels']}
def centroid(rects):
    A = sum((r[2] - r[0]) * (r[3] - r[1]) for r in rects)
    return (sum((r[0] + r[2]) / 2 * (r[2] - r[0]) * (r[3] - r[1]) for r in rects) / A,
            sum((r[1] + r[3]) / 2 * (r[2] - r[0]) * (r[3] - r[1]) for r in rects) / A)
cur = {}   # region -> placement.json path
for r, d in fixed.items(): cur[r] = os.path.join(d, 'placement.json')
RES = json.load(open(a.reserve)) if a.reserve else {}
def anchors_for(region):
    anc = {}
    for n, v in ATTR.items():
        rg = lab2reg.get(v['label'])
        if rg and rg != region: anc[n] = centroid(S[rg]['rects'])
    for rg, p in cur.items():
        if rg == region: continue
        for n, c in json.load(open(p))['cells'].items(): anc[n] = (c['x'] + c['w_sites'] * 0.28, c['y'] + 1.96)
    return anc
order = [r for r in ('dp', 'ctrl', 'div') if r in S and r not in fixed] + [r for r in S if r not in fixed and r not in ('dp', 'ctrl', 'div')]
for ps in range(a.passes):
    for rg in order:
        anc = anchors_for(rg); ap_ = os.path.join(a.out, f'anchors_{rg}.json'); json.dump(anc, open(ap_, 'w'))
        od = os.path.join(a.out, rg)
        cmd = [sys.executable, os.path.join(here, 'region_place.py'), '--netlist', a.netlist, '--attr', a.attr,
               '--labels', *S[rg]['labels'], '--ref-def', a.ref_def, '--out-dir', od, '--anchors', ap_,
               '--iters', iters.get(rg, '150000'), '--seed', str(a.seed)]
        for rc in S[rg]['rects']: cmd += ['--region', *map(str, rc)]
        if ps == 0 and a.seed_from: cmd += ['--init-def', os.path.join(a.seed_from, f'{rg}_prev.def')]
        elif ps == 0: cmd += ['--init-def', a.init_def]
        else: cmd += ['--init-def', os.path.join(a.out, f'{rg}_prev.def')]
        if a.keep_rows: cmd += ['--keep-rows']
        if RES:
            rr = {n: m for n, m in RES.items() if lab2reg.get(ATTR.get(n, {}).get('label')) == rg}
            if rr: rp = os.path.join(a.out, f'reserve_{rg}.json'); json.dump(rr, open(rp, 'w')); cmd += ['--reserve', rp]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode: print(r.stdout[-800:], r.stderr[-1500:]); sys.exit(1)
        m = json.loads(r.stdout)
        print(f"pass {ps} {rg:5s} cells {m['cells']:4d} packing {m['packing_incl_taps']:.2%} (with reservation {m.get('packing_with_reserved_upsizing', 0):.2%}) hpwl {m['hpwl_block_nets_um']:.0f} (init {m['hpwl_initial_um']:.0f})", flush=True)
        cur[rg] = os.path.join(od, 'placement.json')
        # write the current placement as a tiny DEF-like seed for the next pass (COMPONENTS only)
        pl = json.load(open(cur[rg]))['cells']
        with open(os.path.join(a.out, f'{rg}_prev.def'), 'w') as f:
            f.write('VERSION 5.8 ;\nUNITS DISTANCE MICRONS 2000 ;\nDIEAREA ( 0 0 ) ( 693280 321440 ) ;\n')
            f.write(f'COMPONENTS {len(pl)} ;\n')
            for n, c in pl.items(): f.write(f"    - {n} gf180mcu_fd_sc_mcu7t5v0__{c['master']} + PLACED ( {round(c['x'] * 2000)} {round(c['y'] * 2000)} ) {c['orient']} ;\n")
            f.write('END COMPONENTS\nEND DESIGN\n')
# merge
cells, rects, labels, metas = {}, [], [], {}
for rg, p in cur.items():
    P = json.load(open(p)); cells.update(P['cells']); rects += P['meta'].get('rects') or [P['meta']['region']]
    labels += P['meta']['labels']; metas[rg] = {k: P['meta'][k] for k in ('cells', 'cell_area', 'region_area', 'tap_area_in_region', 'packing_incl_taps', 'hpwl_block_nets_um') if k in P['meta']}
    metas[rg]['placement'] = p; metas[rg]['placement_sha16'] = sha(p)
meta = {'labels': labels, 'rects': rects, 'regions': metas, 'spec': a.spec, 'spec_sha16': sha(a.spec), 'passes': a.passes, 'seed': a.seed}
json.dump({'meta': meta, 'cells': cells}, open(os.path.join(a.out, 'placement.json'), 'w'), indent=1)
with open(os.path.join(a.out, 'macro_placement.cfg'), 'w') as f:
    for n, p in sorted(cells.items()): f.write(f"{n} {p['x']:.2f} {p['y']:.2f} {p['orient']}\n")
print('merged', len(cells), 'cells ->', os.path.join(a.out, 'placement.json'))
