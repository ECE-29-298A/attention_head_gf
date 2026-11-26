#!/usr/bin/env python3
"""Row-based custom placement of a set of synthesized cells inside a rectangular region.
usage: region_place.py --netlist N.json --attr ATTR.json --labels L [L ...] --region X0 Y0 X1 Y1
                       --ref-def REF.def --out-dir DIR [--fit right|left|none] [--target 0.90]
                       [--iters 200000] [--seed 1]
- cells: every synthesized cell whose attribution label is in --labels (ties excluded);
- legal by construction: site-aligned, on rows, orientation = row orientation, never on a tap or
  endcap site of REF.def (the same floorplan), cells never straddle a tap;
- --fit right|left: keep the X1 (right) or X0 (left) edge and the row span, and shrink the other
  edge to the narrowest width whose packing (cells + taps inside) is <= --target;
- objective: half-perimeter wirelength of every net touching the block (clock excluded), with
  pins and out-of-block cells fixed at their REF.def positions (anchors); simulated annealing over
  row order (swap / move), whitespace spread evenly in each row so in-place upsizing has room.
Writes placement.json, macro_placement.cfg (MACRO_PLACEMENT_CFG) and manual_global_placements.json."""
import sys, os, json, math, random, argparse, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdlib import lef_sizes, read_def, sha, liberty
SITE, ROWH = 0.56, 3.92
ap = argparse.ArgumentParser()
ap.add_argument('--netlist', required=True); ap.add_argument('--attr', required=True)
ap.add_argument('--labels', nargs='+', required=True); ap.add_argument('--region', nargs=4, type=float, action='append', required=True, help='repeatable: union of row-aligned rectangles')
ap.add_argument('--ref-def', required=True); ap.add_argument('--out-dir', required=True)
ap.add_argument('--fit', default='none'); ap.add_argument('--target', type=float, default=0.90)
ap.add_argument('--iters', type=int, default=200000); ap.add_argument('--seed', type=int, default=1)
ap.add_argument('--init-def', help='seed the row order from these positions (e.g. the h2 global placement), mapped affinely into the region')
ap.add_argument('--t0-scale', type=float, default=0.03, help='initial temperature as a fraction of the mean uphill swap delta')
ap.add_argument('--keep-rows', action='store_true', help='with --init-def from a previous legal placement: keep each cell in its row and order, only re-pack (spill overflow to the nearest row)')
ap.add_argument('--anchors', help='JSON {inst: [x, y]} positions of out-of-block cells; overrides REF.def positions')
ap.add_argument('--reserve', help='JSON {inst: master}: keep room for in-place upsizing to that master (FIRM flow)')
a = ap.parse_args(); random.seed(a.seed)
LEFS = lef_sizes(); LIB = liberty()
R = read_def(a.ref_def)
TOP = json.load(open(a.netlist))['modules']['tt_um_attention_head_gf']
ATTR = json.load(open(a.attr))['cells']
cells = {n: c['type'].split('__')[1] for n, c in TOP['cells'].items()
         if ATTR.get(n, {}).get('label') in a.labels and not c['type'].split('__')[1].startswith('tie')}
assert cells, 'no cells for labels'
X0r = R['rows'][0]['x']
def site_of(x): return round((x - X0r) / SITE)
# blocked sites per row (taps, endcaps)
rows_by_y = {round(r['y'], 3): r for r in R['rows']}
blocked = collections.defaultdict(set)
for n, c in R['comps'].items():
    if n.startswith('TAP_') or n.startswith('PHY_EDGE') or c['master'].startswith(('filltie', 'endcap')):
        s = site_of(c['x']); w = round(LEFS[c['master']][0] / SITE)
        for k in range(s, s + w): blocked[round(c['y'], 3)].add(k)
RECTS = [list(r) for r in a.region]
x0, y0, x1, y1 = RECTS[0]
def region_rows(x0, x1, y0=None, y1=None):
    y0 = RECTS[0][1] if y0 is None else y0; y1 = RECTS[0][3] if y1 is None else y1
    out = []
    for y, r in sorted(rows_by_y.items()):
        if y + 1e-6 >= y0 and y + ROWH <= y1 + 1e-6:
            s0, s1 = max(0, math.ceil(round((x0 - X0r) / SITE, 6))), min(r['n'], math.floor(round((x1 - X0r) / SITE, 6)))
            free, iv, cur = 0, [], None
            for k in range(s0, s1):
                if k in blocked[y]:
                    if cur is not None: iv.append((cur, k)); cur = None
                else:
                    free += 1
                    if cur is None: cur = k
            if cur is not None: iv.append((cur, s1))
            taps = sum(1 for k in range(s0, s1) if k in blocked[y])
            out.append(dict(y=y, orient=r['orient'], iv=iv, s0=s0, s1=s1, free=free, blocked_sites=taps))
    return out
W0 = {n: round(LEFS[m][0] / SITE) for n, m in cells.items()}
RES = json.load(open(a.reserve)) if a.reserve else {}
W = {n: max(W0[n], round(LEFS[RES[n]][0] / SITE)) if n in RES else W0[n] for n in cells}
A_cells = sum(LIB[m]['area'] for m in cells.values())
A_res = A_cells + sum((W[n] - W0[n]) * SITE * ROWH for n in cells)   # area once reserved upsizing is used
def packing(rr, area=None):
    ra = sum((r['s1'] - r['s0']) * SITE * ROWH for r in rr)
    tap = sum(r['blocked_sites'] * SITE * ROWH for r in rr)
    return ((A_res if area is None else area) + tap) / ra, ra, tap
rows = [rw for r in RECTS for rw in region_rows(r[0], r[2], r[1], r[3])]
# nets
bitpos = {}            # fixed anchor points per bit
port_bits = {}
for pn, pd in TOP['ports'].items():
    for i, b in enumerate(pd['bits']):
        nm = pn if len(pd['bits']) == 1 else f'{pn}[{i}]'
        if nm in R['pins']: port_bits.setdefault(b, []).append((R['pins'][nm]['x'], R['pins'][nm]['y']))
clk_bits = set(TOP['ports']['clk']['bits'])
net_cells = collections.defaultdict(list); net_fixed = collections.defaultdict(list)
ANCH = json.load(open(a.anchors)) if a.anchors else {}
for n, c in TOP['cells'].items():
    for pin, bits in c['connections'].items():
        for b in bits:
            if not isinstance(b, int) or b in clk_bits: continue
            if n in cells: net_cells[b].append(n)
            elif n in ANCH:
                net_fixed[b].append(tuple(ANCH[n]))
            else:
                d = R['comps'].get(n)
                if d and d['x'] is not None:
                    net_fixed[b].append((d['x'] + LEFS[d['master']][0] / 2, d['y'] + ROWH / 2))
nets = [b for b in net_cells]
for b in nets:
    net_fixed[b] = net_fixed.get(b, []) + port_bits.get(b, [])
cell_nets = collections.defaultdict(list)
for b in nets:
    for n in set(net_cells[b]): cell_nets[n].append(b)
# initial order: by anchor centroid
def anchor(n):
    pts = [p for b in cell_nets[n] for p in net_fixed[b]]
    if not pts: return (sum((r[0] + r[2]) / 2 for r in RECTS) / len(RECTS), sum((r[1] + r[3]) / 2 for r in RECTS) / len(RECTS))
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
assign = [[] for _ in rows]
def pack(ri, lst, rws=None):
    """x site of each cell in row ri, whitespace spread evenly; None if it does not fit."""
    rws = rws or rows
    iv = rws[ri]['iv']
    def greedy(g):
        pos, k, p = [], 0, None
        for n in lst:
            while True:
                if k >= len(iv): return None
                s, e = iv[k]
                p = s if p is None or p < s else p
                q = p + (g if pos and pos[-1][1] == k else (g // 2 if g else 0))
                if q + W[n] <= e: pos.append((q, k)); p = q + W[n]; break
                k += 1; p = None
        return [q for q, _ in pos]
    base = greedy(0)
    if base is None: return None
    slack = rws[ri]['free'] - sum(W[n] for n in lst)
    g = slack // (len(lst) + 1) if lst else 0
    while g > 0:
        r = greedy(g)
        if r is not None: return r
        g -= 1
    return base
pos = {}
def place_row(ri):
    xs = pack(ri, assign[ri])
    if xs is None: return False
    for n, s in zip(assign[ri], xs): pos[n] = (X0r + s * SITE, rows[ri]['y'])
    return True
SEED = {}; RAWSEED = {}
if a.init_def:
    G = read_def(a.init_def)
    pts = {n: (G['comps'][n]['x'], G['comps'][n]['y']) for n in cells if n in G['comps'] and G['comps'][n]['x'] is not None}
    def pct(v, q): v = sorted(v); return v[min(len(v) - 1, max(0, int(q * (len(v) - 1))))]
    gx0, gx1 = pct([p[0] for p in pts.values()], 0.02), pct([p[0] for p in pts.values()], 0.98)
    gy0, gy1 = pct([p[1] for p in pts.values()], 0.02), pct([p[1] for p in pts.values()], 0.98)
    bx0 = min(r[0] for r in RECTS); bx1 = max(r[2] for r in RECTS); by0 = min(r[1] for r in RECTS); by1 = max(r[3] for r in RECTS)
    RAWSEED.update(pts)
    for n, (gx, gy) in pts.items():
        fx = min(1, max(0, (gx - gx0) / max(1e-6, gx1 - gx0))); fy = min(1, max(0, (gy - gy0) / max(1e-6, gy1 - gy0)))
        SEED[n] = (bx0 + fx * (bx1 - bx0), by0 + fy * (by1 - by0))
def seedpos(n): return SEED.get(n) or anchor(n)
def ffd(rws):
    asg = [[] for _ in rws]
    for n in sorted(cells, key=lambda m: (-W[m], -seedpos(m)[1])):
        ay, ax = seedpos(n)[1], seedpos(n)[0]
        for ri in sorted(range(len(rws)), key=lambda k: (abs(rws[k]['y'] + ROWH / 2 - ay) + (0 if rws[k]['s0'] * SITE + X0r - 1 <= ax <= rws[k]['s1'] * SITE + X0r + 1 else min(abs(rws[k]['s0'] * SITE + X0r - ax), abs(rws[k]['s1'] * SITE + X0r - ax))), k)):
            trial = sorted(asg[ri] + [n], key=lambda m: seedpos(m)[0])
            if pack(ri, trial, rws) is not None:
                asg[ri] = trial; break
        else:
            return None
    return asg
if a.fit in ('right', 'left'):
    best = None
    for k in range(1, site_of(x1) - site_of(x0) + 1):
        xa, xb = (x1 - k * SITE, x1) if a.fit == 'right' else (x0, x0 + k * SITE)
        rr = region_rows(xa, xb)
        if packing(rr)[0] <= a.target and sum(r['free'] for r in rr) >= sum(W.values()) and ffd(rr) is not None:
            best = (xa, xb); break
    assert best, 'region too small for target'
    x0, x1 = best
    RECTS = [[x0, y0, x1, y1]]
    rows = region_rows(x0, x1)
pk, region_area, tap_area = packing(rows, A_cells)
pk_res = packing(rows)[0]
def keep_rows_init(rws):
    asg = [[] for _ in rws]; spill = []
    for n in cells:
        sx, sy = SEED.get(n, (None, None)) if not a.init_def else RAWSEED.get(n, (None, None))
        hit = None
        if sx is not None:
            for k, r in enumerate(rws):
                if abs(r['y'] - sy) < 1e-3 and r['s0'] * SITE + X0r - 1e-3 <= sx < r['s1'] * SITE + X0r: hit = k; break
        (asg[hit].append(n) if hit is not None else spill.append(n))
    for k in range(len(rws)):
        asg[k].sort(key=lambda m: RAWSEED.get(m, (0, 0))[0])
        while asg[k] and pack(k, asg[k], rws) is None:
            m = min(asg[k], key=lambda c: W[c]); asg[k].remove(m); spill.append(m)
    for n in sorted(spill, key=lambda m: -W[m]):
        sy = RAWSEED.get(n, anchor(n))[1]
        for k in sorted(range(len(rws)), key=lambda k: abs(rws[k]['y'] - sy)):
            trial = sorted(asg[k] + [n], key=lambda m: RAWSEED.get(m, anchor(m))[0])
            if pack(k, trial, rws) is not None: asg[k] = trial; break
        else: return None
    return asg
assign = keep_rows_init(rows) if a.keep_rows else ffd(rows)
if assign is None: raise SystemExit('cell mix does not fit the region (tap fragmentation)')
for ri in range(len(rows)): assert place_row(ri)
row_of = {n: ri for ri, lst in enumerate(assign) for n in lst}
def center(n): return (pos[n][0] + W0[n] * SITE / 2, pos[n][1] + ROWH / 2)
def hpwl(b):
    pts = [center(n) for n in net_cells[b]] + net_fixed[b]
    if len(pts) < 2: return 0.0
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return max(xs) - min(xs) + max(ys) - min(ys)
cost_net = {b: hpwl(b) for b in nets}
total = sum(cost_net.values()); init_total = total
cells_l = list(cells)
import bisect
rowx = [(r['y'] + ROWH / 2, X0r + r['s0'] * SITE, X0r + r['s1'] * SITE) for r in rows]
def target(n):
    """centre of the other pins' bounding boxes of n's nets (the classic optimal-region estimate)"""
    xs, ys = [], []
    for b in cell_nets[n]:
        pts = [center(m) for m in net_cells[b] if m != n] + net_fixed[b]
        if not pts: continue
        px = [q[0] for q in pts]; py = [q[1] for q in pts]
        xs.append((min(px) + max(px)) / 2); ys.append((min(py) + max(py)) / 2)
    if not xs: return None
    xs.sort(); ys.sort()
    return xs[len(xs) // 2], ys[len(ys) // 2]
def nearest_slot(tx, ty):
    k = min(range(len(rows)), key=lambda i: abs(rowx[i][0] - ty) + max(0, rowx[i][1] - tx, tx - rowx[i][2]))
    lst = assign[k]
    if not lst: return k, 0
    xs = [pos[c][0] for c in lst]
    return k, min(len(lst) - 1, bisect.bisect_left(xs, tx))
def try_move(n1, mode):
    r1 = row_of[n1]; old_assign = {}
    if mode == 'target':
        t = target(n1)
        if t is None: return None
        r2, i2 = nearest_slot(*t)
        if random.random() < 0.5 and assign[r2]:
            n2 = assign[r2][i2]
            if n2 == n1: return None
            for r in {r1, r2}: old_assign[r] = list(assign[r])
            j1, j2 = assign[r1].index(n1), assign[r2].index(n2)
            assign[r1][j1], assign[r2][j2] = n2, n1
        else:
            for r in {r1, r2}: old_assign[r] = list(assign[r])
            assign[r1].remove(n1); assign[r2].insert(min(i2, len(assign[r2])), n1)
    elif mode == 'swap':
        n2 = random.choice(cells_l); r2 = row_of[n2]
        if n1 == n2: return None
        for r in {r1, r2}: old_assign[r] = list(assign[r])
        j1, j2 = assign[r1].index(n1), assign[r2].index(n2)
        assign[r1][j1], assign[r2][j2] = n2, n1
    else:   # neighbour swap in the same row
        lst = assign[r1]; j = lst.index(n1)
        if len(lst) < 2: return None
        k = j + 1 if j + 1 < len(lst) else j - 1
        old_assign[r1] = list(lst); lst[j], lst[k] = lst[k], lst[j]
    return old_assign
def evaluate(old_assign):
    old_pos = {n: pos[n] for r in old_assign for n in old_assign[r]}
    if not all(place_row(r) for r in old_assign): return None, old_pos, None
    touched = {b for r in old_assign for n in assign[r] for b in cell_nets[n]}
    new = {b: hpwl(b) for b in touched}
    return sum(new[b] - cost_net[b] for b in touched), old_pos, new
def undo(old_assign, old_pos):
    for r, lst in old_assign.items(): assign[r] = lst
    pos.update(old_pos)
    for r in old_assign:
        for n in assign[r]: row_of[n] = r
# initial temperature from the mean uphill delta of random swaps
ups = []
for _ in range(min(300, 3 * len(cells_l))):
    oa = try_move(random.choice(cells_l), 'swap')
    if not oa: continue
    d, op, _ = evaluate(oa); undo(oa, op)
    if d is not None and d > 0: ups.append(d)
T0 = a.t0_scale * ((sum(ups) / len(ups)) if ups else 1.0); Tend = T0 * 1e-3
for it in range(a.iters):
    T = T0 * (Tend / T0) ** (it / max(1, a.iters))
    u = random.random(); mode = 'target' if u < 0.6 else ('swap' if u < 0.85 else 'nbr')
    n1 = random.choice(cells_l)
    oa = try_move(n1, mode)
    if not oa: continue
    d, op, new = evaluate(oa)
    if d is not None and (d <= 0 or random.random() < math.exp(-d / T)):
        for b, v in new.items(): cost_net[b] = v
        total += d
        for r in oa:
            for n in assign[r]: row_of[n] = r
    else:
        undo(oa, op)
total = sum(hpwl(b) for b in nets)
os.makedirs(a.out_dir, exist_ok=True)
pl = {n: {'x': round(pos[n][0], 3), 'y': round(pos[n][1], 3), 'orient': rows[row_of[n]]['orient'],
          'master': cells[n], 'w_sites': W0[n], 'w_res_sites': W[n], 'reserved_master': RES.get(n)} for n in sorted(cells)}
meta = {'labels': a.labels, 'region': [round(x0, 3), y0, round(x1, 3), y1] if len(RECTS) == 1 else None,
        'rects': [[round(v, 3) for v in r] for r in RECTS], 'rows': len(rows),
        'cells': len(cells), 'cell_area': round(A_cells, 3), 'tap_area_in_region': round(tap_area, 3),
        'region_area': round(region_area, 3), 'packing_incl_taps': round(pk, 4), 'packing_with_reserved_upsizing': round(pk_res, 4),
        'hpwl_block_nets_um': round(total, 1), 'hpwl_initial_um': round(init_total, 1), 'nets': len(nets),
        'netlist': a.netlist, 'netlist_sha16': sha(a.netlist), 'anchors': a.anchors, 'init_def': a.init_def, 'ref_def': a.ref_def, 'ref_def_sha16': sha(a.ref_def),
        'seed': a.seed, 'iters': a.iters, 'reserve': RES,
        'reserved_extra_area': round(sum((W[n] - W0[n]) * SITE * ROWH for n in cells), 3)}
json.dump({'meta': meta, 'cells': pl}, open(os.path.join(a.out_dir, 'placement.json'), 'w'), indent=1)
with open(os.path.join(a.out_dir, 'macro_placement.cfg'), 'w') as f:
    for n, p in pl.items(): f.write(f"{n} {p['x']:.2f} {p['y']:.2f} {p['orient']}\n")
json.dump({n: {'location': [p['x'], p['y']], 'orientation': p['orient']} for n, p in pl.items()},
          open(os.path.join(a.out_dir, 'manual_global_placements.json'), 'w'), indent=1)
print(json.dumps(meta, indent=1))
