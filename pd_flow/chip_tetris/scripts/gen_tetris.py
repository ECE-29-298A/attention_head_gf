#!/usr/bin/env python3
"""Whole-chip tetris generator (from the datapath-cluster generator): seed from the tool's own placement of the
reference run (wc_ref), improve the movable cells (default: every synthesized cell of the chip) with legal moves only.

usage: gen_tetris.py --out DIR [--reserve R.json ...] [--iters N] [--seed S] [--T0 T]
                     [--weights flat|repair] [--repair-from CLASSES.json ...] [--K 4]
                     [--slices] [--slice-w W] [--ring] [--edge] [--movable dp|all]
Steps:
  1. s0 = h2 final sites/orientations of all 1,416 non-tie cells; h2's upsizes reserved at their
     h2 masters (legal by construction);
  2. extra reservations (probe results) added with dplib.reserve (row-local legalization);
  3. optional structure (see PLAN.md): --slices bit-slice column term for S[i] slices;
  4. legal-move annealing of the movable cells on weighted HPWL (dpo.DPO);
  5. validation (dplib.Placement.check) and output (placement.json, macro_placement.cfg,
     manual_global_placements.json, reserve.json, gen.json).
"""
import sys, os, json, argparse, time, collections, re
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import dplib, dpo

ap = argparse.ArgumentParser()
ap.add_argument('--out', required=True); ap.add_argument('--reserve', nargs='*', default=[])
ap.add_argument('--iters', type=int, default=0); ap.add_argument('--seed', type=int, default=1)
ap.add_argument('--T0', type=float, default=1.0); ap.add_argument('--T1', type=float, default=0.005)
ap.add_argument('--weights', default='flat'); ap.add_argument('--repair-from', nargs='*', default=[])
ap.add_argument('--K', type=float, default=4.0)
ap.add_argument('--crit', help='crit.py JSON: add D10 item-4 weights 1 + Kc*min(crit_rsz,2)^2 + Ks*min(crit_sig,2)^2 (max with the repair weights)')
ap.add_argument('--Kc', type=float, default=10.0); ap.add_argument('--Ks', type=float, default=5.0)
ap.add_argument('--K2', type=float, default=0.0, help='weight for repaired-driver nets whose seed HPWL >= --hpwl-thr (wire-sensitive)')
ap.add_argument('--hpwl-thr', type=float, default=60.0)
ap.add_argument('--slices', action='store_true'); ap.add_argument('--slice-w', type=float, default=0.3)
ap.add_argument('--movable', default='all', help='all (whole chip, default) | dp | union | b')
ap.add_argument('--pack-set', default='all', help='cells whose per-row extent the compaction term and the footprint measure: all | dp'); ap.add_argument('--window-rows', type=int, default=3)
ap.add_argument('--window-sites', type=int, default=40)
ap.add_argument('--init', help='start from this placement dir instead of s0')
ap.add_argument('--hinge-frac', type=float, default=0.0, help='HPWL target = frac x (seed HPWL scaled by GPL/legal) for repaired-driver nets')
ap.add_argument('--hinge-w', type=float, default=0.0)
ap.add_argument('--sensitive-from', nargs='*', default=[], help='BASE.json S1.json ...: hinge only the nets of drivers whose '
                'upsize+repair differs from BASE in at least one S (placement-sensitive resizer decisions)')
ap.add_argument('--freeze-flops', action='store_true', help='keep the dp flops at their seed sites (clock sinks unchanged)')
ap.add_argument('--hinge-json', help='{net: HPWL target um}: explicit hinge targets (weight --hinge-w), e.g. from targets.py')
ap.add_argument('--pack-w', type=float, default=0.0, help='D8c compaction: weight per um of the cluster row extent (sum over rows)')
ap.add_argument('--ring', type=float, default=0.0, help='O0 ring as an array: ring flops movable (even with --freeze-flops) and every ring shift net (flop Q -> flop D) weighted x RING')
ap.add_argument('--edge', type=float, default=0.0, help='edge alignment: nets joining the cluster to div/ctrl cells weighted x EDGE (their pins stay at tool positions)')
ap.add_argument('--relocate', nargs='*', default=[], help='cell:x:y ... explicit relocations (CTS sink-cluster moves), each into the cheapest existing free gap near (x, y) um, applied before annealing')
ap.add_argument('--seed-def', help='seed from this DEF of the reference run (e.g. its step-34 DPL DEF) instead of its final DEF')
a = ap.parse_args()
t0 = time.time()
d = dplib.Design()
if a.seed_def:
    d.h2 = dplib.read_def(a.seed_def)['comps']; d.def_path = a.seed_def
P = dplib.Placement.load(d, a.init) if a.init else dplib.seed_from_h2(d)
log = []
def say(s):
    print(s, flush=True); log.append(s)
W = dplib.Wire(P); say(f'seed {"h2" if not a.init else a.init}: HPWL {W.total():.1f}')
# reservations ---------------------------------------------------------------------------------
res = {}
for rp in a.reserve:
    for n, m in json.load(open(rp)).items():
        if n not in res or d.wsites(m) > d.wsites(res[n]): res[n] = m
need = {n: m for n, m in res.items() if n in P.cells and d.wsites(m) > P.cells[n]['wr']}
newrm = {n: m for n, m in res.items() if n in P.cells and P.cells[n].get('rm') != m and d.wsites(m) <= P.cells[n]['wr']}
for n, m in newrm.items():
    if P.cells[n].get('rm') is None or d.wsites(m) >= d.wsites(P.cells[n]['rm']): P.cells[n]['rm'] = m
moved_res = dplib.reserve(P, need) if need else []
say(f'reservations: {sum(1 for c in P.cells.values() if c.get("rm"))} cells, widened now {len(need)}, cells shifted {len(moved_res)}')
for spec in a.relocate:
    n, x, y = spec.split(':'); x, y = float(x), float(y)
    x_pref = dplib.site_of(x) - P.cells[n]['wr'] // 2
    g = dplib.find_gap(P, n, dplib.row_of(y), x_pref, max_rows=1)
    if g and g[0] < 4.0 and (g[1], g[2]) != (P.cells[n]['r'], P.cells[n]['s']):
        dplib.move_to(P, n, g[1], g[2]); how = 'free gap'
    else:
        disp = dplib.block_swap(P, n, dplib.row_of(y), dplib.site_of(x), max_rows=1,
                                protect={q for q in P.cells if d.master[q].startswith('dff')})   # a flop-for-flop swap leaves the CTS sink set unchanged
        if disp is None: say(f'relocate {n}: no run near ({x}, {y})'); sys.exit(1)
        how = f'block swap with {disp}'
    say(f'relocate {n} -> near ({x}, {y}): {how}; now row {P.cells[n]["r"]} site {P.cells[n]["s"]} {P.def_xy(n)}')
# movable set ------------------------------------------------------------------------------------
if a.movable == 'dp':
    mov = d.dp
elif a.movable == 'union':     # structural dp + Architect B's in-context dp attribution (h2 only)
    A = json.load(open(dplib.ATTR_JSON))['cells']
    mov = sorted(set(d.dp) | {n for n in d.custom if A.get(n, {}).get('label') in dplib.DP_LABELS})
elif a.movable == 'b':
    A = json.load(open(dplib.ATTR_JSON))['cells']
    mov = sorted(n for n in d.custom if A.get(n, {}).get('label') in dplib.DP_LABELS)
else:
    mov = d.custom
RING_Q = re.compile(r'^(core\.mac\.ring\[|core\.divider_unit\.sum_in\[|core\.divider_unit\.magnitude\[0\])')
ring = {f for q, f in d.flop_q.items() if RING_Q.match(q)}
if a.freeze_flops:
    mov = [n for n in mov if not d.master[n].startswith('dff') or (a.ring and n in ring)]
say(f'movable cells: {len(mov)}')
# weights ----------------------------------------------------------------------------------------
wt = {}
if a.weights == 'repair':
    drv = set()
    for cp in a.repair_from:
        C = json.load(open(cp))
        C = C.get('area_classes', C)
        drv |= set(C['upsized']) | set(C['repair_by_driver'])
    for n in drv:
        if n not in d.master: continue
        for p, b in d.conns[n].items():
            if d.pdir(d.master[n], p) == 'output':
                wt[b] = a.K
                if a.K2 and W.net(b) >= a.hpwl_thr: wt[b] = a.K2
    say(f'weights: {len(wt)} repaired-driver nets x{a.K}, of which {sum(1 for v in wt.values() if v == a.K2)} wire-sensitive (seed HPWL >= {a.hpwl_thr} um) x{a.K2}')
if a.crit:
    CJ = json.load(open(a.crit)); n_c = 0
    for b, r in CJ['rsz'].items():
        g = CJ['sig'].get(b, r)
        w = 1.0 + a.Kc * min(r['crit'], 2.0) ** 2 + a.Ks * min(g['crit'], 2.0) ** 2
        if w > wt.get(b, 1.0): wt[b] = w; n_c += 1
    say(f'crit weights from {a.crit}: {n_c} nets raised (Kc {a.Kc}, Ks {a.Ks}); nets with weight > 10: {sum(1 for v in wt.values() if v > 10)}')
if a.ring:
    nr = 0
    for f in ring:
        b = d.conns[f].get('D')
        if b in d.flop_q and d.flop_q[b] in ring:
            wt[b] = max(wt.get(b, 1.0), a.ring); nr += 1
    say(f'ring: {len(ring)} ring flops movable, {nr} shift nets x{a.ring}')
if a.edge:
    dps = set(d.dp); ne = 0
    for b, lst in d.nets.items():
        if b == d.clk: continue
        cs = {n for n, _ in lst}
        if cs & dps and (cs - dps - d.ties):
            wt[b] = max(wt.get(b, 1.0), a.edge); ne += 1
    say(f'edge: {ne} cluster-boundary nets x{a.edge}')
tgt = {}
if a.hinge_frac and wt:
    import glob
    G = dplib.read_def(glob.glob(d.ref + '/28-openroad-globalplacement/*.def')[0])['comps']
    def chp(C, b):
        pts = [(C[n]['x'] + d.LEFS[C[n]['master']][0] / 2, C[n]['y']) for n, _ in d.nets[b] if n in C and C[n]['x'] is not None]
        pts += d.port_pts.get(b, [])
        return (max(q[0] for q in pts) - min(q[0] for q in pts) + max(q[1] for q in pts) - min(q[1] for q in pts)) if len(pts) > 1 else 0.0
    hset = set(wt)
    if a.sensitive_from:
        L = d.LIB
        def ld(p):
            j = json.load(open(p)); return j.get('area_classes', j)
        def cost(C, n):
            u = C['upsized'].get(n); return (u[2] if u else 0) + sum(L[m]['area'] for _, m in C['repair_by_driver'].get(n, []))
        base = ld(a.sensitive_from[0]); sens = set()
        for sp in a.sensitive_from[1:]:
            C = ld(sp)
            for n in set(base['upsized']) | set(base['repair_by_driver']) | set(C['upsized']) | set(C['repair_by_driver']):
                if abs(cost(base, n) - cost(C, n)) > 1e-6: sens.add(n)
        hset = set()
        for n in sens:
            if n in d.master:
                hset |= {b for p, b in d.conns[n].items() if d.pdir(d.master[n], p) == 'output'}
        say(f'placement-sensitive drivers: {len(sens)} {sorted(sens)}')
    for b in hset:
        g, l = chp(G, b), chp(d.h2, b)
        if l > 1.0:
            tgt[b] = a.hinge_frac * W.net(b) * min(1.0, g / l)
    say(f'hinge targets: {len(tgt)} nets, frac {a.hinge_frac} x seed HPWL x (GPL/legal), weight {a.hinge_w}')
if a.hinge_json:
    HJ = json.load(open(a.hinge_json)); HJ = HJ.get('targets', HJ)
    for b, t in HJ.items():
        if b in d.nets: tgt[b] = min(tgt.get(b, 1e9), float(t))
    say(f'explicit hinge targets from {a.hinge_json}: {len(HJ)} nets, weight {a.hinge_w}')
# slices -----------------------------------------------------------------------------------------
slices, cols = {}, None
if a.slices:
    # bit i: S[i] flop (Q=core.exponent_unit.D[i]), M[i] flop (Q=core.mac.M[i]) and the dp cells that
    # are adjacent (one net) to exactly one bit's S/M flop pair
    bitflop = {}
    for i in range(22):
        for nm in (f'core.exponent_unit.D[{i}]', f'core.mac.M[{i}]'):
            if nm in d.flop_q: bitflop[d.flop_q[nm]] = i
    adj = collections.defaultdict(set)
    for f, i in bitflop.items():
        for b in d.cell_nets[f]:
            if len(d.nets[b]) > 12: continue
            for m, _ in d.nets[b]:
                if m in d.dp and m not in bitflop: adj[m].add(i)
    for f, i in bitflop.items(): slices[f] = i
    for m, bits in adj.items():
        if len(bits) == 1: slices[m] = next(iter(bits))
    # column x per bit: current mean x of the slice cells, then made monotonic in bit order
    xs = collections.defaultdict(list)
    for m, i in slices.items():
        x, _ = P.def_xy(m); xs[i].append(x)
    raw = [sum(xs[i]) / len(xs[i]) if xs[i] else None for i in range(22)]
    order = sorted(range(22), key=lambda i: raw[i] if raw[i] is not None else 0)
    lo, hi = min(r for r in raw if r is not None), max(r for r in raw if r is not None)
    # keep the h2 direction (LSB side), evenly spaced between the observed extremes
    lsb_left = (raw[0] or 0) < (raw[21] or 0)
    cols = {i: lo + (hi - lo) * (i if lsb_left else 21 - i) / 21 for i in range(22)}
    say(f'slices: {len(slices)} cells over 22 bits, columns {lo:.1f}..{hi:.1f} um, LSB {"west" if lsb_left else "east"}')
# optimize ---------------------------------------------------------------------------------------
if a.iters:
    O = dpo.DPO(P, mov, wt, seed=a.seed, slices=slices, slice_w=a.slice_w if a.slices else 0.0, slice_cols=cols,
                window_rows=a.window_rows, window_sites=a.window_sites, targets=tgt, hinge_w=a.hinge_w,
                pack_set=(d.custom if a.pack_set == 'all' else d.dp), pack_w=a.pack_w)
    c0 = O.cost_total(); h0 = O.hpwl_total()
    O.run(a.iters, a.T0, a.T1, log=say, every=max(1, a.iters // 5))
    say(f'optimizer: cost {c0:.1f} -> {O.cost_total():.1f}, movable-net HPWL {h0:.1f} -> {O.hpwl_total():.1f}')
errs = P.check()
if errs:
    say('ERRORS: ' + '; '.join(errs[:10])); sys.exit(1)
W = dplib.Wire(P)
h2 = dplib.seed_from_h2(d)
disp = sorted(((abs(P.cells[n]['r'] - h2.cells[n]['r']) * dplib.ROWH + abs(P.def_xy(n)[0] - h2.def_xy(n)[0]), n) for n in d.custom), reverse=True)
moved = [n for dd, n in disp if dd > 1e-6]
import footprint as _fp
meta = {'generator': 'gen_tetris.py', 'args': vars(a), 'hpwl_pins_um': round(W.total(), 1),
        'footprint': _fp.footprint(d, P, (d.custom if a.pack_set == 'all' else d.dp)),
        'footprint_seed': _fp.footprint(d, h2, (d.custom if a.pack_set == 'all' else d.dp)),
        'cells_moved_from_h2': len(moved), 'dp_moved': sum(1 for n in moved if n in set(d.dp)),
        'nondp_moved': [n for n in moved if n not in set(d.dp)],
        'mean_disp_um': round(sum(dd for dd, _ in disp) / len(disp), 3), 'max_disp_um': round(disp[0][0], 2),
        'reserved': sum(1 for c in P.cells.values() if c.get('rm')), 'seconds': round(time.time() - t0, 1),
        'netlist_sha16': dplib.SYN_SHA16, 'log': log}
P.write(a.out, meta)
json.dump(meta, open(os.path.join(a.out, 'gen.json'), 'w'), indent=1)
say(f'wrote {a.out}: HPWL {W.total():.1f}, moved {len(moved)} (non-dp {len(meta["nondp_moved"])}), mean disp {meta["mean_disp_um"]} um')
