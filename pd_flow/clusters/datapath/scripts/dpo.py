"""Legal-move detailed placement optimizer (simulated annealing) for the datapath tetris.

Every move keeps the placement legal by construction (spans on free sites, no tap/endcap site,
row orientation), so the result needs no legalization:
  - relocate: move a cell's span into a free run of sites near the centre of its nets' other pins;
  - swap: exchange the spans of two movable cells of the same span width;
  - flip: toggle mirroring (N<->FN, FS<->S);
  - slide: shift a cell inside the free run around it.
Cost: sum over nets of weight * HPWL (pin centres, clock excluded; non-movable pins fixed), plus an
optional alignment term that pulls the cells of each S[i] bit slice toward a common column.
"""
import math, random, collections
import dplib
from dplib import SITE, ROWH, X0, Y0, NROWS, NSITES, MIRRORED, legal_orients


class DPO:
    def __init__(self, P, movable, weights=None, seed=1, slices=None, slice_w=0.0, slice_cols=None,
                 window_rows=3, window_sites=40, targets=None, hinge_w=0.0, pack_set=None, pack_w=0.0):
        self.P, self.d = P, P.d
        self.mov = sorted(movable)
        self.movset = set(self.mov)
        self.rng = random.Random(seed)
        self.wt = weights or {}
        self.tgt = targets or {}      # net -> HPWL target (um); cost adds hinge_w * max(0, HPWL - target)
        self.hw = hinge_w
        self.wr_, self.ws_ = window_rows, window_sites
        d = self.d
        # per-orientation pin offsets
        self.off = {}
        for n in P.cells:
            m = P.cells[n]['m']; W, H = d.LEFS[m]
            for o in ('N', 'FN', 'FS', 'S'):
                tab = {}
                for pin, (px, py) in d.PINS.get(m, {}).items():
                    if o == 'FN': px = W - px
                    elif o == 'FS': py = H - py
                    elif o == 'S': px, py = W - px, H - py
                    tab[pin] = (px, py)
                self.off[(n, o)] = tab
        self.wsite = {n: d.wsites(P.cells[n]['m']) for n in P.cells}
        # nets touching movable cells
        self.nets = {}
        self.cnets = collections.defaultdict(list)
        fixedw = dplib.Wire(P)   # for fixed pin lists
        for b, lst in d.nets.items():
            if b == d.clk: continue
            mv = [(n, p) for n, p in lst if n in self.movset]
            if not mv: continue
            fx = list(fixedw.fixed[b]) + [P.pin_xy(n, p) for n, p in lst if n in P.cells and n not in self.movset]
            self.nets[b] = (mv, fx)
            for n in set(n for n, _ in mv): self.cnets[n].append(b)
        # occupancy
        self.occ = [[None] * NSITES for _ in range(NROWS)]
        for r in range(NROWS):
            for k in d.blocked[r]: self.occ[r][k] = '#'
        for n, c in P.cells.items():
            for k in range(c['s'], c['s'] + c['wr']):
                assert self.occ[c['r']][k] is None, f'overlap at {n}'
                self.occ[c['r']][k] = n
        self.pos = {}
        for n in P.cells: self._setpos(n)
        self.hp = {b: self._hpwl(b) for b in self.nets}
        # slices: {cell: bit}; columns: target x per bit (um), optional
        self.slices = slices or {}
        self.slice_w = slice_w
        self.slice_cols = slice_cols
        self.by_width = collections.defaultdict(list)
        for n in self.mov: self.by_width[P.cells[n]['wr']].append(n)
        # compaction (D8c): pack_w x sum over rows of the cluster's row extent (um) = region area / ROWH
        self.pack_w = pack_w
        self.pset = set(pack_set or ())
        self.prow = collections.defaultdict(set)
        for n in self.pset: self.prow[P.cells[n]['r']].add(n)
        self.pext = {r: self._row_ext(r) for r in range(NROWS)}

    # geometry -------------------------------------------------------------------------------
    def _setpos(self, n):
        c = self.P.cells[n]
        cs = c['s'] + (c['wr'] - self.wsite[n] if c['o'] in MIRRORED else 0)
        self.pos[n] = (X0 + cs * SITE, Y0 + c['r'] * ROWH, c['o'])

    def _pin(self, n, p):
        x, y, o = self.pos[n]
        ox, oy = self.off[(n, o)].get(p, (self.wsite[n] * SITE / 2, ROWH / 2))
        return x + ox, y + oy

    def _hpwl(self, b):
        mv, fx = self.nets[b]
        xs = [q[0] for q in fx]; ys = [q[1] for q in fx]
        for n, p in mv:
            x, y = self._pin(n, p); xs.append(x); ys.append(y)
        if len(xs) < 2: return 0.0
        return max(xs) - min(xs) + max(ys) - min(ys)

    def _hinge(self, b, v):
        t = self.tgt.get(b)
        return self.hw * max(0.0, v - t) if t is not None else 0.0

    def cost_total(self):
        c = sum(self.wt.get(b, 1.0) * v + self._hinge(b, v) for b, v in self.hp.items())
        return c + self.slice_cost_all() + self.pack_w * sum(self.pext.values())

    def _row_ext(self, r):
        lst = self.prow.get(r)
        if not lst: return 0.0
        lo = min(self.pos[n][0] for n in lst)
        hi = max(self.pos[n][0] + self.wsite[n] * SITE for n in lst)
        return hi - lo

    def region_sites(self):
        return sum(self.pext.values()) / SITE

    def hpwl_total(self):
        return sum(self.hp.values())

    # slice alignment --------------------------------------------------------------------------
    def slice_cost_all(self):
        if not self.slice_w or not self.slices: return 0.0
        return sum(self._slice_cost(n) for n in self.slices if n in self.movset)

    def _slice_cost(self, n):
        if not self.slice_w or n not in self.slices or self.slice_cols is None: return 0.0
        x = self.pos[n][0] + self.wsite[n] * SITE / 2
        return self.slice_w * abs(x - self.slice_cols[self.slices[n]])

    # move machinery ---------------------------------------------------------------------------
    def _free_run(self, r, s, wr, me):
        if s < 0 or s + wr > NSITES: return False
        row = self.occ[r]
        for k in range(s, s + wr):
            v = row[k]
            if v is not None and v != me: return False
        return True

    def _put(self, n, r, s, o):
        c = self.P.cells[n]
        for k in range(c['s'], c['s'] + c['wr']):
            if self.occ[c['r']][k] == n: self.occ[c['r']][k] = None
        c['r'], c['s'], c['o'] = r, s, o
        for k in range(s, s + c['wr']): self.occ[r][k] = n
        self._setpos(n)

    def _target(self, n):
        xs, ys = [], []
        for b in self.cnets[n]:
            mv, fx = self.nets[b]
            px = [q[0] for q in fx]; py = [q[1] for q in fx]
            for m, p in mv:
                if m == n: continue
                x, y = self._pin(m, p); px.append(x); py.append(y)
            if not px: continue
            xs.append((min(px) + max(px)) / 2); ys.append((min(py) + max(py)) / 2)
        if not xs: return None
        xs.sort(); ys.sort()
        return xs[len(xs) // 2], ys[len(ys) // 2]

    def _delta(self, cells):
        nets = set()
        for n in cells: nets.update(self.cnets[n])
        new = {b: self._hpwl(b) for b in nets}
        dc = sum(self.wt.get(b, 1.0) * (new[b] - self.hp[b]) + self._hinge(b, new[b]) - self._hinge(b, self.hp[b]) for b in nets)
        return dc, new

    def _orient_for(self, n, r):
        mir = self.P.cells[n]['o'] in MIRRORED
        return legal_orients(r)[1 if mir else 0]

    def step(self, T):
        n = self.rng.choice(self.mov)
        c = self.P.cells[n]
        u = self.rng.random()
        old = {n: (c['r'], c['s'], c['o'])}
        sc_old = self._slice_cost(n)
        if u < 0.55:      # relocate near target
            t = self._target(n)
            if t is None: return 0
            tr = min(NROWS - 1, max(0, int(round((t[1] - ROWH / 2 - Y0) / ROWH))))
            ts = int(round((t[0] - X0) / SITE - c['wr'] / 2))
            r = min(NROWS - 1, max(0, tr + self.rng.randint(-self.wr_ // 3 - 1, self.wr_ // 3 + 1)))
            s0 = ts + self.rng.randint(-8, 8)
            best = None
            for dd in range(0, self.ws_):
                for s in (s0 - dd, s0 + dd):
                    if self._free_run(r, s, c['wr'], n):
                        best = s; break
                if best is not None: break
            if best is None or (r, best) == (c['r'], c['s']): return 0
            self._put(n, r, best, self._orient_for(n, r))
            moved = [n]
        elif u < 0.85:    # swap with a same-width cell near the target
            pool = self.by_width[c['wr']]
            if len(pool) < 2: return 0
            t = self._target(n)
            m = None
            for _ in range(12):
                q = self.rng.choice(pool)
                if q == n: continue
                if t is None or (abs(self.pos[q][0] - t[0]) < self.ws_ * SITE and abs(self.pos[q][1] - t[1]) < self.wr_ * ROWH):
                    m = q; break
            if m is None: return 0
            cm = self.P.cells[m]
            old[m] = (cm['r'], cm['s'], cm['o'])
            rn, sn = c['r'], c['s']; rm, sm = cm['r'], cm['s']
            on, om = self._orient_for(n, rm), self._orient_for(m, rn)
            # clear both, then put
            for k in range(sn, sn + c['wr']): self.occ[rn][k] = None
            for k in range(sm, sm + cm['wr']): self.occ[rm][k] = None
            c['r'], c['s'], c['o'] = rm, sm, on; cm['r'], cm['s'], cm['o'] = rn, sn, om
            for k in range(sm, sm + c['wr']): self.occ[rm][k] = n
            for k in range(sn, sn + cm['wr']): self.occ[rn][k] = m
            self._setpos(n); self._setpos(m)
            moved = [n, m]
            sc_old += self._slice_cost_old_m(m, old[m])
        elif u < 0.93:    # flip
            o = c['o']; flip = {'N': 'FN', 'FN': 'N', 'FS': 'S', 'S': 'FS'}[o]
            c['o'] = flip; self._setpos(n); moved = [n]
        else:             # slide inside the free run
            r = c['r']; lo = c['s']; hi = c['s'] + c['wr']
            while lo > 0 and self.occ[r][lo - 1] is None: lo -= 1
            while hi < NSITES and self.occ[r][hi] is None: hi += 1
            if hi - lo == c['wr']: return 0
            s = self.rng.randint(lo, hi - c['wr'])
            if s == c['s']: return 0
            self._put(n, r, s, c['o']); moved = [n]
        dc, new = self._delta(moved)
        sc_new = sum(self._slice_cost(q) for q in moved)
        dc += sc_new - sc_old
        pmv = [q for q in moved if q in self.pset] if self.pack_w else []
        newext = {}
        if pmv:
            rows = set()
            for q in pmv:
                ro = old[q][0]; rn = self.P.cells[q]['r']; rows |= {ro, rn}
                if ro != rn: self.prow[ro].discard(q); self.prow[rn].add(q)
            newext = {r: self._row_ext(r) for r in rows}
            dc += self.pack_w * sum(newext[r] - self.pext[r] for r in rows)
        if dc <= 0 or (T > 0 and self.rng.random() < math.exp(-dc / T)):
            self.hp.update(new); self.pext.update(newext)
            return dc
        for q in pmv:
            ro = old[q][0]; rn = self.P.cells[q]['r']
            if ro != rn: self.prow[rn].discard(q); self.prow[ro].add(q)
        # undo
        for q in moved:
            cq = self.P.cells[q]
            for k in range(cq['s'], cq['s'] + cq['wr']):
                if self.occ[cq['r']][k] == q: self.occ[cq['r']][k] = None
        for q in moved:
            r, s, o = old[q]; cq = self.P.cells[q]
            cq['r'], cq['s'], cq['o'] = r, s, o
            for k in range(s, s + cq['wr']): self.occ[r][k] = q
            self._setpos(q)
        return 0

    def _slice_cost_old_m(self, m, oldrso):
        if not self.slice_w or m not in self.slices or self.slice_cols is None: return 0.0
        r, s, o = oldrso
        cs = s + (self.P.cells[m]['wr'] - self.wsite[m] if o in MIRRORED else 0)
        x = X0 + cs * SITE + self.wsite[m] * SITE / 2
        return self.slice_w * abs(x - self.slice_cols[self.slices[m]])

    def run(self, iters, T0=2.0, T1=0.01, log=None, every=50000):
        c0 = self.cost_total()
        for i in range(iters):
            T = T0 * (T1 / T0) ** (i / max(1, iters - 1))
            self.step(T)
            if log and (i + 1) % every == 0:
                log(f'  it {i + 1:7d} T {T:.3f} cost {self.cost_total():.1f} hpwl {self.hpwl_total():.1f}')
        return c0, self.cost_total()
