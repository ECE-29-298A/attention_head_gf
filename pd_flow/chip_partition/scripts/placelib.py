#!/usr/bin/env python3
"""Site-grid occupancy model of the TT 1x1 GF180 core (Architect A, pd_flow/chip_partition).

Rows: 39, y = 3.92 + 3.92 r; sites: 607, x = 3.36 + 0.56 s (from the h2 DEF ROW statements,
asserted). Fixed physical cells (filltie taps, endcaps) are taken from a reference DEF; the flow
re-inserts them at the same positions (deterministic tapcell on the same floorplan).
Used by the pilot generator to (a) check a full placement (on-site, in-core, no overlap, no tap
overlap) and (b) move a cell to the nearest legal gap.
"""
import os, sys, bisect
sys.path.insert(0, os.path.dirname(__file__))
import pdlib

X0, Y0, SW, RH, NS, NR = 3.36, 3.92, 0.56, 3.92, 607, 39


def to_site(x):
    s = (x - X0) / SW
    assert abs(s - round(s)) < 1e-6, x
    return int(round(s))


def to_row(y):
    r = (y - Y0) / RH
    assert abs(r - round(r)) < 1e-6, y
    return int(round(r))


def row_orient(r):
    return "N" if r % 2 == 0 else "FS"


class Grid:
    def __init__(self, ref_def):
        D = pdlib.parse_def(ref_def, want_routes=False)
        assert len(D["rows"]) == NR and all(r["n"] == NS for r in D["rows"])
        assert abs(D["rows"][0]["x"] - X0) < 1e-9 and abs(D["rows"][0]["y"] - Y0) < 1e-9
        self.L = pdlib.lef_macros()
        self.rows = [dict() for _ in range(NR)]   # site -> (name, width) start map
        self.occ = [[None] * NS for _ in range(NR)]
        self.fixed_phys = {}
        for n, c in D["comps"].items():
            m = c["master"].replace(pdlib.PFX, "")
            if m in ("filltie", "endcap"):
                self.place(n, c["master"], c["x"], c["y"], phys=True)
                self.fixed_phys[n] = (c["master"], c["x"], c["y"], c["orient"])

    def width_sites(self, master):
        w = self.L[master]["w"] / SW
        assert abs(w - round(w)) < 1e-6, master
        return int(round(w))

    def place(self, name, master, x, y, phys=False):
        s, r, w = to_site(x), to_row(y), self.width_sites(master)
        assert 0 <= r < NR and 0 <= s and s + w <= NS, (name, x, y)
        clash = {self.occ[r][k] for k in range(s, s + w) if self.occ[r][k] is not None}
        for k in range(s, s + w):
            if self.occ[r][k] is None:
                self.occ[r][k] = name
        return clash

    def remove(self, name, master, x, y):
        s, r, w = to_site(x), to_row(y), self.width_sites(master)
        for k in range(s, s + w):
            if self.occ[r][k] == name:
                self.occ[r][k] = None

    def overlaps(self, name, master, x, y):
        s, r, w = to_site(x), to_row(y), self.width_sites(master)
        return {self.occ[r][k] for k in range(s, s + w) if self.occ[r][k] not in (None, name)}

    def find_spot(self, master, x, y, max_rows=39, forbid=None):
        """Nearest (Manhattan, um) free span for master around (x, y); forbid(r, s, w) -> bool."""
        w = self.width_sites(master)
        s0, r0 = to_site(x), to_row(y)
        best = None
        for dr in range(0, max_rows):
            if best and dr * RH > best[0]:
                break
            for r in {r0 - dr, r0 + dr}:
                if not 0 <= r < NR:
                    continue
                run = 0
                for s in range(NS):
                    run = run + 1 if self.occ[r][s] is None else 0
                    if run >= w:
                        st = s - w + 1
                        if forbid and forbid(r, st, w):
                            continue
                        d = abs(st - s0) * SW + abs(r - r0) * RH
                        if best is None or d < best[0]:
                            best = (d, r, st)
        assert best, (master, x, y)
        d, r, s = best
        return X0 + s * SW, Y0 + r * RH, row_orient(r), d

    def free_sites(self, r, s0=0, s1=NS):
        return sum(1 for k in range(s0, s1) if self.occ[r][k] is None)


def segments(G, r):
    """Maximal [a, b) site ranges of row r not covered by fixed physical cells (taps/endcaps)."""
    segs, a = [], None
    for s in range(NS):
        phys = G.occ[r][s] is not None and G.occ[r][s] in G.fixed_phys
        if not phys and a is None:
            a = s
        if phys and a is not None:
            segs.append((a, s))
            a = None
    if a is not None:
        segs.append((a, NS))
    return segs


def slide_insert(G, cells, name, master, x, y, max_rows=3, clip=None):
    """Insert `name` (width of `master`) at/near (x, y) by order-preserving 1-D re-legalization of
    the movable cells in one tap segment (cells: dict name -> [master, x, y, orient], updated in
    place, must hold every placed non-physical cell). Tries the target row first, then +-1.. rows.
    Returns (displacement sum in um, list of moved names) or None if no segment has capacity."""
    w = G.width_sites(master)
    s_t, r0 = to_site(x), to_row(y)
    best = None
    byrow = {}
    for n, v in cells.items():
        if n != name:
            byrow.setdefault(to_row(v[2]), []).append((n, v))
    for dr in range(0, max_rows + 1):
        for r in sorted({r0 - dr, r0 + dr}):
            if not 0 <= r < NR:
                continue
            spans = []
            for a, b in segments(G, r):
                spans += clip(r, a, b) if clip else [(a, b)]
            for a, b in spans:
                mem = [(n, v) for n, v in byrow.get(r, []) if a <= to_site(v[1]) < b]
                if any(to_site(v[1]) + G.width_sites(v[0]) > b for _, v in mem):
                    continue  # a cell straddles the clip boundary: span not usable
                used = sum(G.width_sites(v[0]) for _, v in mem)
                if used + w > b - a:
                    continue
                tgt = min(max(s_t, a), b - w)
                items = sorted([(to_site(v[1]), n, G.width_sites(v[0])) for n, v in mem] + [(tgt, name, w)],
                               key=lambda t: (t[0], t[1] != name))
                pos = []
                cur = a
                for s, n, ww in items:      # left-to-right clamp
                    p = max(s, cur)
                    pos.append([p, n, ww])
                    cur = p + ww
                nxt = b
                for it in reversed(pos):    # right-to-left clamp
                    it[0] = min(it[0], nxt - it[2])
                    nxt = it[0]
                assert pos[0][0] >= a
                disp = sum(abs(p - (s_t if n == name else to_site(cells[n][1]))) * SW for p, n, _ in pos) \
                    + abs(r - r0) * RH
                if best is None or disp < best[0]:
                    best = (disp, r, [(p, n) for p, n, _ in pos])
        if best is not None and best[0] < (dr + 1) * RH:
            break
    if best is None:
        return None
    disp, r, layout = best
    moved = []
    for p, n in layout:
        if n == name:
            continue
        v = cells[n]
        if to_site(v[1]) != p:
            G.remove(n, v[0], v[1], v[2])
            v[1] = X0 + p * SW
            moved.append(n)
    for p, n in layout:
        if n == name:
            continue
        v = cells[n]
        if n in moved:
            G.place(n, v[0], v[1], v[2])
    p = dict((nn, pp) for pp, nn in layout)[name]
    mirrored = name in cells and cells[name][3] in ("FN", "S")
    o = row_orient(r)
    o = {"N": "FN", "FS": "S"}[o] if mirrored else o
    cells[name] = [master, X0 + p * SW, Y0 + r * RH, o]
    clash = G.place(name, master, X0 + p * SW, Y0 + r * RH)
    assert not clash, clash
    return disp, moved
