"""Datapath-cluster tetris: shared library (host python3, no third-party packages).

Netlist-agnostic: everything is derived from one *reference run* (env DP_REF, default h2
/Users/samuelzhang/ttharden/fx_h2_k6/runs/wokwi):
  - its synthesized netlist 06-yosys-synthesis/*.nl.v (instances, masters, nets by name);
  - its final DEF (the tool's own placement = the seed; taps, endcaps and pins);
  - the dp cluster by structure (attribute.py: flops by the public name of their Q net,
    combinational cells by the flops their fan-out cone reaches), never by instance name.
GF180 7-track LEF / Liberty via Architect B's pdlib.

Placement model.  A custom cell occupies a *span* of `wr` sites starting at site `s` in row `r`; the
cell itself is `w` sites wide.  wr > w only for a cell with an upsizing reservation.  An in-place
master swap keeps the instance origin (measured, dp_work/scr/swaptest2.tcl): N/FS cells grow to the
right, FN/S (mirrored) cells grow to the left.  So the cell sits left-aligned in its span when its
orientation is N/FS and right-aligned when FN/S.
"""
import sys, os, re, json, collections, hashlib, math, glob

REPO = '/Users/samuelzhang/Desktop/2B ECE/attention_head_gf'
BDIR = os.path.join(REPO, 'pd_flow', 'chip_partition_b')
sys.path.insert(0, os.path.join(BDIR, 'tools'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdlib import read_def, lef_sizes, liberty, sha, PFX, LEF  # noqa: E402
import attribute  # noqa: E402

H2 = '/Users/samuelzhang/ttharden/fx_h2_k6/runs/wokwi'
X0RUN = '/Users/samuelzhang/ttharden/md_x0_full/runs/wokwi'
REF = os.environ.get('DP_REF', H2)
REF_TAG = os.environ.get('DP_REF_TAG', 'h2' if REF == H2 else ('x0' if REF == X0RUN else os.path.basename(os.path.dirname(os.path.dirname(REF)))))
REF_DEF = glob.glob(REF + '/final/def/*.def')[0]
REF_SYN_NL = glob.glob(REF + '/06-yosys-synthesis/*.nl.v')[0]
H2_DEF = H2 + '/final/def/tt_um_attention_head_gf.def'
H2_SYN_NL = H2 + '/06-yosys-synthesis/tt_um_attention_head_gf.nl.v'
ATTR_JSON = os.path.join(BDIR, 'connectivity', 'h2_attribution.json')   # Architect B (h2 only, cross-check)
SYN_SHA16 = sha(REF_SYN_NL)
SITE, ROWH, X0, Y0 = 0.56, 3.92, 3.36, 3.92
NROWS, NSITES = 39, 607
DP_LABELS = ('core.mac', 'core.mac.adder', 'core.mac.l_adder', 'core.max_unit', 'core.exponent_unit')
MIRRORED = ('FN', 'S')


def row_orient(r):
    return 'N' if r % 2 == 0 else 'FS'


def legal_orients(r):
    return ('N', 'FN') if r % 2 == 0 else ('FS', 'S')


def site_of(x):
    return int(round((x - X0) / SITE))


def row_of(y):
    return int(round((y - Y0) / ROWH))


def lef_pins(path=LEF):
    """{short master: {pin: (cx, cy)}} centre of the bounding box of each signal pin's port shapes."""
    out, cur, pin, rects = {}, None, None, []
    for line in open(path):
        t = line.split()
        if not t:
            continue
        if t[0] == 'MACRO':
            cur = t[1].replace(PFX, ''); out[cur] = {}
        elif t[0] == 'PIN' and cur:
            pin, rects = t[1], []
        elif t[0] == 'RECT' and pin:
            v = [float(z) for z in t[1:5]]; rects.append(v)
        elif t[0] == 'END' and len(t) > 1 and pin and t[1] == pin:
            if rects:
                out[cur][pin] = ((min(r[0] for r in rects) + max(r[2] for r in rects)) / 2,
                                 (min(r[1] for r in rects) + max(r[3] for r in rects)) / 2)
            pin = None
    return out


class Design:
    """The frozen reference netlist and floorplan (nets keyed by name)."""

    def __init__(self, ref=None):
        self.ref = ref or REF
        nl = glob.glob(self.ref + '/06-yosys-synthesis/*.nl.v')[0]
        self.nl_path, self.nl_sha16 = nl, sha(nl)
        self.def_path = glob.glob(self.ref + '/final/def/*.def')[0]
        self.LIB = liberty(); self.LEFS = lef_sizes(); self.PINS = lef_pins()
        C = attribute.parse_nl(nl)
        self.master = {n: m for n, (m, _) in C.items()}
        self.syn = self.master
        self.conns = {n: dict(p) for n, (_, p) in C.items()}
        self.clk = 'clk'
        self.netname = collections.defaultdict(lambda: None)
        self.D = read_def(self.def_path)
        self.h2 = self.D['comps']          # seed placement (the reference run's final DEF)
        self.port_pts = collections.defaultdict(list)
        self.port_of_bit = {}
        for pn, pd in self.D['pins'].items():
            self.port_pts[pd['net']].append((pd['x'], pd['y']))
            self.port_of_bit[pd['net']] = pn
        self.nets = collections.defaultdict(list)    # net -> [(cell, pin)]
        self.driver = {}
        for n, cs in self.conns.items():
            for p, b in cs.items():
                self.nets[b].append((n, p))
                if self.pdir(self.master[n], p) == 'output':
                    self.driver[b] = (n, p)
        for b in self.nets:
            self.netname[b] = b
        self.cell_nets = collections.defaultdict(set)
        for b, lst in self.nets.items():
            if b == self.clk:
                continue
            for n, _ in lst:
                self.cell_nets[n].add(b)
        lab, self.attr_how = attribute.attribute(C, self.pdir)
        self.label = lab                     # 'dp' | 'other' | 'tie'
        self.ties = {n for n, m in self.master.items() if m.startswith('tie')}
        self.custom = sorted(n for n in self.master if n not in self.ties)   # FIRM cells
        self.dp = sorted(n for n in self.custom if self.label[n] == 'dp')
        self.blocked = collections.defaultdict(set)
        for n, c in self.h2.items():
            if n.startswith(('TAP_', 'PHY_EDGE')):
                s = site_of(c['x']); w = self.wsites(c['master'])
                for k in range(s, s + w):
                    self.blocked[row_of(c['y'])].add(k)
        self.flop_q = {}
        for n, m in self.master.items():
            if m.startswith('dff') and 'Q' in self.conns[n]:
                self.flop_q[self.conns[n]['Q']] = n

    def pdir(self, m, p):
        return self.LIB[m]['pins'].get(p, {}).get('dir')

    def wsites(self, m):
        return int(round(self.LEFS[m][0] / SITE))

    def area(self, m):
        return self.LIB[m]['area']


class Placement:
    """cells[n] = dict(r, s, wr, o, m, rm): row, span start site, span width (sites), orientation,
    synthesized master, reserved master (or None)."""

    def __init__(self, design, cells=None, meta=None):
        self.d = design
        self.cells = cells or {}
        self.meta = meta or {}

    def copy(self):
        return Placement(self.d, {n: dict(c) for n, c in self.cells.items()}, dict(self.meta))

    # geometry ---------------------------------------------------------------------------------
    def w(self, n):
        return self.d.wsites(self.cells[n]['m'])

    def cell_site(self, n):
        c = self.cells[n]
        return c['s'] + (c['wr'] - self.w(n) if c['o'] in MIRRORED else 0)

    def def_xy(self, n):
        c = self.cells[n]
        return (round(X0 + self.cell_site(n) * SITE, 3), round(Y0 + c['r'] * ROWH, 3))

    def pin_xy(self, n, pin):
        """pin centre of a custom cell (orientation-aware)."""
        c = self.cells[n]; m = c['m']
        x, y = self.def_xy(n)
        W, H = self.d.LEFS[m]
        px, py = self.d.PINS.get(m, {}).get(pin, (W / 2, H / 2))
        o = c['o']
        if o == 'FN': px = W - px
        elif o == 'FS': py = H - py
        elif o == 'S': px, py = W - px, H - py
        return (x + px, y + py)

    # legality ---------------------------------------------------------------------------------
    def check(self, require_set=True):
        """returns a list of errors (empty = legal)."""
        errs = []
        if require_set and not self.meta.get("partial_firm") and set(self.cells) != set(self.d.custom):
            errs.append(f'cell set mismatch: missing {sorted(set(self.d.custom) - set(self.cells))[:5]} '
                        f'extra {sorted(set(self.cells) - set(self.d.custom))[:5]}')
        occ = collections.defaultdict(list)
        for n, c in self.cells.items():
            if c['m'] != self.d.master.get(n):
                errs.append(f'{n}: master {c["m"]} != synthesized {self.d.master.get(n)}')
            if not 0 <= c['r'] < NROWS:
                errs.append(f'{n}: row {c["r"]}'); continue
            if c['o'] not in legal_orients(c['r']):
                errs.append(f'{n}: orient {c["o"]} in row {c["r"]}')
            if c['wr'] < self.w(n):
                errs.append(f'{n}: span {c["wr"]} < width {self.w(n)}')
            if c.get('rm') and self.d.wsites(c['rm']) > c['wr']:
                errs.append(f'{n}: reserved master {c["rm"]} wider than span')
            if c['s'] < 0 or c['s'] + c['wr'] > NSITES:
                errs.append(f'{n}: outside the row')
            bl = self.d.blocked[c['r']]
            if any(k in bl for k in range(c['s'], c['s'] + c['wr'])):
                errs.append(f'{n}: span on a tap/endcap site')
            occ[c['r']].append((c['s'], c['s'] + c['wr'], n))
        for r, lst in occ.items():
            lst.sort()
            for (a0, a1, an), (b0, b1, bn) in zip(lst, lst[1:]):
                if b0 < a1:
                    errs.append(f'overlap {an} / {bn} in row {r}')
        return errs

    def row_lists(self):
        rows = collections.defaultdict(list)
        for n, c in self.cells.items():
            rows[c['r']].append(n)
        for r in rows:
            rows[r].sort(key=lambda n: self.cells[n]['s'])
        return rows

    def free_mask(self, r, exclude=()):
        """list of booleans, True where site k of row r is free (no tap/endcap, no span)."""
        f = [k not in self.d.blocked[r] for k in range(NSITES)]
        for n, c in self.cells.items():
            if c['r'] == r and n not in exclude:
                for k in range(c['s'], c['s'] + c['wr']):
                    f[k] = False
        return f

    # output -----------------------------------------------------------------------------------
    def to_json(self):
        out = {}
        for n in sorted(self.cells):
            c = self.cells[n]; x, y = self.def_xy(n)
            out[n] = {'x': x, 'y': y, 'orient': c['o'], 'master': c['m'], 'w_sites': self.w(n),
                      'w_res_sites': c['wr'], 'span_site': c['s'], 'row': c['r'], 'reserved_master': c.get('rm')}
        return out

    def write(self, outdir, meta=None):
        os.makedirs(outdir, exist_ok=True)
        pj = self.to_json()
        m = dict(self.meta); m.update(meta or {})
        json.dump({'meta': m, 'cells': pj}, open(os.path.join(outdir, 'placement.json'), 'w'), indent=1)
        with open(os.path.join(outdir, 'macro_placement.cfg'), 'w') as f:
            for n, p in pj.items():
                f.write(f"{n} {p['x']:.2f} {p['y']:.2f} {p['orient']}\n")
        json.dump({n: {'location': [p['x'], p['y']], 'orientation': p['orient']} for n, p in pj.items()},
                  open(os.path.join(outdir, 'manual_global_placements.json'), 'w'), indent=1)
        json.dump({n: p['reserved_master'] for n, p in pj.items() if p['reserved_master']},
                  open(os.path.join(outdir, 'reserve.json'), 'w'), indent=1, sort_keys=True)

    @staticmethod
    def load(design, pdir):
        P = json.load(open(os.path.join(pdir, 'placement.json')))
        cells = {n: dict(r=v['row'], s=v['span_site'], wr=v['w_res_sites'], o=v['orient'], m=v['master'],
                         rm=v.get('reserved_master')) for n, v in P['cells'].items()}
        return Placement(design, cells, P['meta'])


def seed_from_h2(d):
    """s0: every non-tie synthesized cell at its h2 final site, row and orientation; a cell the
    resizer upsized in h2 reserves its h2 final master (the h2 final placement is legal for it)."""
    cells = {}
    for n in d.custom:
        c = d.h2[n]
        r, s = row_of(c['y']), site_of(c['x'])
        wf = d.wsites(c['master'])
        cells[n] = dict(r=r, s=s, wr=max(wf, d.wsites(d.master[n])), o=c['orient'], m=d.master[n],
                        rm=c['master'] if c['master'] != d.master[n] else None)
    return Placement(d, cells, {'seed': f'{REF_TAG} final DEF (the tool placement)', 'seed_def': d.def_path,
                                'seed_def_sha16': sha(d.def_path), 'netlist': d.nl_path, 'netlist_sha16': d.nl_sha16})


# wirelength --------------------------------------------------------------------------------------
class Wire:
    """Incremental HPWL (pin centres, clock excluded).  Non-custom cells (ties, and anything not in
    the placement) sit at their h2 final position."""

    def __init__(self, P, weights=None):
        self.P, self.d = P, P.d
        self.wt = weights or {}
        self.fixed = collections.defaultdict(list)
        for b, lst in self.d.nets.items():
            if b == self.d.clk:
                continue
            for n, p in lst:
                if n not in P.cells:
                    c = self.d.h2.get(n)
                    if c is None:        # ties: re-created under new names by repair_tie_fanout
                        continue
                    W, H = self.d.LEFS[c['master']]
                    self.fixed[b].append((c['x'] + W / 2, c['y'] + H / 2))
            self.fixed[b] += self.d.port_pts.get(b, [])
        self.cache = {b: self.net(b) for b in self.d.nets if b != self.d.clk}

    def net(self, b):
        pts = [self.P.pin_xy(n, p) for n, p in self.d.nets[b] if n in self.P.cells] + self.fixed[b]
        if len(pts) < 2:
            return 0.0
        xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
        return max(xs) - min(xs) + max(ys) - min(ys)

    def total(self, weighted=False):
        if weighted:
            return sum(v * self.wt.get(b, 1.0) for b, v in self.cache.items())
        return sum(self.cache.values())

    def delta(self, cells):
        """weighted delta of moving `cells` (positions already updated in P); returns (delta, new)."""
        nets = set()
        for n in cells:
            nets |= self.d.cell_nets[n]
        new = {b: self.net(b) for b in nets}
        return sum((new[b] - self.cache[b]) * self.wt.get(b, 1.0) for b in nets), new

    def commit(self, new):
        self.cache.update(new)


# local legalization ------------------------------------------------------------------------------
def segments(d, r):
    """maximal runs [a, b) of non-blocked sites in row r."""
    out, a = [], None
    for k in range(NSITES + 1):
        free = k < NSITES and k not in d.blocked[r]
        if free and a is None: a = k
        if not free and a is not None: out.append((a, k)); a = None
    return out


def abacus(items, lo, hi):
    """items: [(name, width, target_start)] in the fixed left-to-right order; returns {name: start}
    minimising sum (start - target)^2 subject to no overlap inside [lo, hi), integer sites; None if
    the widths do not fit."""
    if sum(w for _, w, _ in items) > hi - lo:
        return None
    clusters = []   # [first_index, last_index, total_width, sum_e, sum_q]  (e=1 per cell)
    for i, (n, w, t) in enumerate(items):
        clusters.append([i, i, w, 1.0, float(t)])
        while True:
            c = clusters[-1]
            x = min(max(c[4] / c[3], lo), hi - c[2])
            if len(clusters) > 1:
                p = clusters[-2]
                px = min(max(p[4] / p[3], lo), hi - p[2])
                if px + p[2] > x:
                    # merge c into p: offsets of c's cells shift by p's width
                    p[1] = c[1]; p[4] += c[4] - c[3] * p[2]; p[3] += c[3]; p[2] += c[2]
                    clusters.pop(); continue
            break
    out = {}
    for c in clusters:
        x = int(round(min(max(c[4] / c[3], lo), hi - c[2])))
        x = min(max(x, lo), hi - c[2])
        for i in range(c[0], c[1] + 1):
            out[items[i][0]] = x; x += items[i][1]
    return out


def legalize_row(P, r, targets=None, pinned=()):
    """re-legalize every custom cell of row r segment by segment, keeping the left-to-right order;
    targets: {name: desired span start} (default: current).  Returns True on success."""
    d = P.d; targets = targets or {}
    lst = sorted((n for n, c in P.cells.items() if c['r'] == r),
                 key=lambda n: (targets.get(n, P.cells[n]['s']) + P.cells[n]['wr'] / 2.0))
    for a, b in segments(d, r):
        seg = [n for n in lst if a <= targets.get(n, P.cells[n]['s']) + P.cells[n]['wr'] / 2.0 < b]
        if not seg: continue
        sol = abacus([(n, P.cells[n]['wr'], min(max(targets.get(n, P.cells[n]['s']), a), b - P.cells[n]['wr'])) for n in seg], a, b)
        if sol is None:
            return False
        for n, s in sol.items():
            P.cells[n]['s'] = s
    return True


def overflow_segments(P, r, targets=None):
    """segments of row r whose assigned cells do not fit: [(a, b, [names])]."""
    d = P.d; targets = targets or {}; out = []
    lst = [n for n, c in P.cells.items() if c['r'] == r]
    for a, b in segments(d, r):
        seg = [n for n in lst if a <= targets.get(n, P.cells[n]['s']) + P.cells[n]['wr'] / 2.0 < b]
        if sum(P.cells[n]['wr'] for n in seg) > b - a:
            out.append((a, b, seg))
    return out


def find_gap(P, n, r_pref, x_pref, max_rows=4, avoid=None):
    """cheapest existing free gap (no shifting) for cell n's span, rows within max_rows of r_pref;
    avoid = (row, a, b) site range that must not be used.  Returns (cost_um, row, site) or None."""
    c = P.cells[n]; wr = c['wr']; best = None
    for r in range(max(0, r_pref - max_rows), min(NROWS, r_pref + max_rows + 1)):
        f = P.free_mask(r, exclude=(n,))
        if avoid and avoid[0] == r:
            for k in range(max(0, avoid[1]), min(NSITES, avoid[2])):
                f[k] = False
        run = 0
        for k in range(NSITES):
            run = run + 1 if f[k] else 0
            if run >= wr:
                s = k - wr + 1
                cost = abs(s - x_pref) * SITE + abs(r - r_pref) * ROWH
                if best is None or cost < best[0]:
                    best = (cost, r, s)
    return best


def move_to(P, n, r, s):
    c = P.cells[n]; mir = c['o'] in MIRRORED
    c['r'], c['s'] = r, s
    c['o'] = legal_orients(r)[1 if mir else 0]


def place_in_gap(P, n, r_pref, x_pref, max_rows=4, avoid=None):
    best = find_gap(P, n, r_pref, x_pref, max_rows, avoid)
    if best is None:
        return False
    move_to(P, n, best[1], best[2])
    return True


def reserve(P, resized, max_iter=6):
    """give every cell in `resized` ({name: master}) a span wide enough for that master, growing on
    the side the in-place swap grows (right for N/FS, left for FN/S), shifting row neighbours
    (order kept) and, if a tap segment overflows, moving its smallest other cell to the nearest gap.
    Returns the list of cells displaced."""
    d = P.d; moved = set()
    before = {n: (c['r'], c['s'], c['o']) for n, c in P.cells.items()}
    rows = set()
    for n, m in resized.items():
        c = P.cells[n]; need = d.wsites(m)
        cur_rm = c.get('rm')
        if cur_rm is None or d.wsites(m) >= d.wsites(cur_rm):
            c['rm'] = m
        if need > c['wr']:
            if c['o'] in MIRRORED: c['s'] -= need - c['wr']
            c['wr'] = need
        rows.add(c['r'])
    for _ in range(max_iter):
        bad = False
        for r in sorted(rows):
            for a, b, seg in overflow_segments(P, r):
                bad = True
                over = sum(P.cells[n]['wr'] for n in seg) - (b - a)
                cand = [n for n in seg if n not in resized]
                if not cand: raise RuntimeError(f'row {r} segment {a}-{b} cannot fit reserved cells')
                # evict the cell (wide enough to clear the overflow if possible) with the cheapest gap
                opts = []
                for v in cand:
                    g = find_gap(P, v, r, P.cells[v]['s'], avoid=(r, a, b))
                    if g: opts.append((P.cells[v]['wr'] < over, g[0], v, g))
                if not opts: raise RuntimeError(f'no gap to relieve row {r} segment {a}-{b}')
                _, _, v, g = min(opts)
                move_to(P, v, g[1], g[2]); moved.add(v)
                rows.add(g[1])
            if not legalize_row(P, r):
                bad = True
        if not bad and not P.check(require_set=False):
            break
    errs = P.check(require_set=False)
    if errs:
        raise RuntimeError('reserve() left errors: ' + '; '.join(errs[:5]))
    for n, c in P.cells.items():
        if (c['r'], c['s'], c['o']) != before[n]:
            moved.add(n)
    return sorted(moved)
