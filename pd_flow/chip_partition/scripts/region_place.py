#!/usr/bin/env python3
"""region_place.py <base_pilot_dir> <attribution.json> <module> <out_dir> --rect r0,r1,s0,s1 [--passes N]

Netlist-driven generator (gen2) that places one in-context module inside one rectangular region of the
1x1 core; it replaces region_pack.py's affine map (gen1, rejected: pre-route HPWL +42 % against P1).
  1. analytic: quadratic (clique-model) wirelength minimum of the module's cells, with every other cell
     and the TT pins as fixed anchors at their base positions (nets with > 40 pins and clk are skipped);
  2. spreading: recursive bisection of the region by free-site capacity (taps/endcaps excluded), cells
     split in analytic order by area, so each cell gets a target in the region;
  3. legalization: first-fit-decreasing of cells into (row, tap-segment) bins nearest their targets,
     each bin ordered by target x with its slack spread evenly (whole sites, row orientation kept);
  4. improvement: greedy same-width swaps inside the region that lower HPWL (N passes);
  5. foreign cells inside the region: moved to the HPWL-optimal (median) point of their nets, then
     order-preserving in-row insertion outside the region (placelib.slide_insert, clipped).
Writes <out_dir>/relocate.json (for make_pilot.py --relocate) and <out_dir>/relocate_report.json.
"""
import json, os, re, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import pdlib, placelib as P
import region_pack as RP

H2DEF = "/Users/samuelzhang/ttharden/fx_h2_k6/runs/wokwi/final/def/tt_um_attention_head_gf.def"


def main():
    a = sys.argv[1:]
    i = a.index("--rect")
    r0, r1, s0, s1 = [int(v) for v in a[i + 1].split(",")]
    del a[i:i + 2]
    passes = 4
    if "--passes" in a:
        i = a.index("--passes")
        passes = int(a[i + 1])
        del a[i:i + 2]
    pdir, attr, module, outdir = a
    os.makedirs(outdir, exist_ok=True)
    masters, pos = RP.load_base(pdir)
    mem = sorted(set(RP.module_members(pdir, attr, module, masters)))
    L = pdlib.lef_macros()
    G = P.Grid(H2DEF)
    w = {n: G.width_sites(masters[n]) for n in masters}
    cw = {n: L[masters[n]]["w"] for n in masters}
    ch = {n: L[masters[n]]["h"] for n in masters}
    # nets
    txt = open(os.path.join(pdir, "pilot.v")).read()
    D = pdlib.parse_def(H2DEF, want_routes=False)
    nets = defaultdict(list)
    for m, n, body in re.findall(r"^\s*(gf180mcu_fd_sc_mcu7t5v0__\w+)\s+(\S+)\s*\((.*?)\);", txt, re.M | re.S):
        n = n.replace("\\", "")
        for p, v in re.findall(r"\.(\w+)\s*\(\s*([^()]*?)\s*\)", body):
            v = v.replace("\\", "").strip()
            if v and v != "clk" and not v.startswith("1'b"):
                nets[v].append(n)
    pinxy = {v: (D["pins"][v]["x"], D["pins"][v]["y"]) for v in nets if v in D["pins"]}
    cell_nets = defaultdict(list)
    for v, ns in nets.items():
        for n in set(ns):
            cell_nets[n].append(v)
    cur = {n: [pos[n][0], pos[n][1], pos[n][2]] for n in pos}     # lower-left x, y, orient

    def ctr(n):
        return cur[n][0] + cw[n] / 2, cur[n][1] + ch[n] / 2

    def net_hpwl(v):
        pts = [ctr(n) for n in set(nets[v])]
        if v in pinxy:
            pts.append(pinxy[v])
        if len(pts) < 2:
            return 0.0
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return max(xs) - min(xs) + max(ys) - min(ys)

    def total_hpwl():
        return sum(net_hpwl(v) for v in nets)
    hp0 = total_hpwl()
    # ---- 1. analytic
    idx = {n: k for k, n in enumerate(mem)}
    N = len(mem)
    A = np.zeros((N, N))
    bx, by = np.zeros(N), np.zeros(N)
    for v, ns in nets.items():
        ns = sorted(set(ns))
        pts_fixed = [ctr(n) for n in ns if n not in idx]
        if v in pinxy:
            pts_fixed.append(pinxy[v])
        mv = [idx[n] for n in ns if n in idx]
        k = len(ns) + (1 if v in pinxy else 0)
        if not mv or k < 2 or k > 40:
            continue
        wt = 2.0 / k
        for ii, p in enumerate(mv):
            for q in mv[ii + 1:]:
                A[p, p] += wt; A[q, q] += wt; A[p, q] -= wt; A[q, p] -= wt
            for fx, fy in pts_fixed:
                A[p, p] += wt; bx[p] += wt * fx; by[p] += wt * fy
    cx, cy = P.X0 + (s0 + s1) / 2 * P.SW, P.Y0 + (r0 + r1) / 2 * P.RH
    for p in range(N):            # weak pull to the region centre (regularisation)
        A[p, p] += 1e-3; bx[p] += 1e-3 * cx; by[p] += 1e-3 * cy
    X, Y = np.linalg.solve(A, bx), np.linalg.solve(A, by)
    ana = {n: (X[idx[n]], Y[idx[n]]) for n in mem}
    # ---- 2. recursive bisection spreading over free-site capacity
    phys = np.array([[G.occ[r][s] is not None for s in range(P.NS)] for r in range(P.NR)])
    capm = (~phys).astype(int)
    tgt = {}

    def cap(ra, rb, sa, sb):
        return int(capm[ra:rb, sa:sb].sum())

    def bisect(cells, ra, rb, sa, sb):
        if not cells:
            return
        if (rb - ra == 1 and (sb - sa) <= 40) or len(cells) == 1:
            for n in cells:
                tgt[n] = ((sa + sb) / 2 - w[n] / 2, ra + (rb - ra - 1) / 2)
            return
        horiz = (sb - sa) * P.SW >= (rb - ra) * P.RH and sb - sa >= 2
        if not horiz and rb - ra < 2:
            horiz = True
        if horiz:
            # split columns so the two capacities are about equal
            tot = cap(ra, rb, sa, sb)
            m = sa + 1
            while m < sb - 1 and cap(ra, rb, sa, m) < tot / 2:
                m += 1
            c1, c2 = cap(ra, rb, sa, m), cap(ra, rb, m, sb)
            order = sorted(cells, key=lambda n: ana[n][0])
        else:
            m = (ra + rb) // 2
            c1, c2 = cap(ra, m, sa, sb), cap(m, rb, sa, sb)
            order = sorted(cells, key=lambda n: ana[n][1])
        area = sum(w[n] for n in order)
        acc, k = 0, 0
        while k < len(order) and acc + w[order[k]] / 2 <= area * c1 / (c1 + c2):
            acc += w[order[k]]
            k += 1
        if horiz:
            bisect(order[:k], ra, rb, sa, m); bisect(order[k:], ra, rb, m, sb)
        else:
            bisect(order[:k], ra, m, sa, sb); bisect(order[k:], m, rb, sa, sb)
    bisect(list(mem), r0, r1, s0, s1)
    # ---- 3. FFD legalization into (row, tap segment) bins
    bins = []
    for r in range(r0, r1):
        a_ = None
        for s in range(s0, s1):
            if not phys[r, s] and a_ is None:
                a_ = s
            if phys[r, s] and a_ is not None:
                bins.append((r, a_, s)); a_ = None
        if a_ is not None:
            bins.append((r, a_, s1))
    rem = [b_ - a_ for _, a_, b_ in bins]
    content = [[] for _ in bins]
    for n in sorted(mem, key=lambda n: (-w[n], tgt[n][1], tgt[n][0])):
        best = None
        for k, (r, a_, b_) in enumerate(bins):
            if rem[k] < w[n]:
                continue
            c = abs(min(max(tgt[n][0], a_), b_ - w[n]) - tgt[n][0]) + abs(r - tgt[n][1]) * (P.RH / P.SW)
            if best is None or c < best[0]:
                best = (c, k)
        assert best, ("region too small", n)
        content[best[1]].append(n)
        rem[best[1]] -= w[n]

    def orient(n, r):
        o = P.row_orient(r)
        return {"N": "FN", "FS": "S"}[o] if pos[n][2] in ("FN", "S") else o

    def lay_bin(k):
        r, a_, b_ = bins[k]
        cs = sorted(content[k], key=lambda n: tgt[n][0])
        slack = (b_ - a_) - sum(w[n] for n in cs)
        x = a_
        for j, n in enumerate(cs):
            x += slack * (j + 1) // (len(cs) + 1) - slack * j // (len(cs) + 1)
            cur[n] = [P.X0 + x * P.SW, P.Y0 + r * P.RH, orient(n, r)]
            x += w[n]
        assert x <= b_
    for k in range(len(bins)):
        lay_bin(k)
    binof = {n: k for k in range(len(bins)) for n in content[k]}
    hp_legal = None
    # ---- 5 (before 4, so swaps see final neighbours). foreign cells inside the region
    inside = lambda r, s, ww: r0 <= r < r1 and s < s1 and s + ww > s0
    memset = set(mem)
    displaced = [n for n in pos if n not in memset and inside(P.to_row(pos[n][1]), P.to_site(pos[n][0]), w[n])]
    occ = P.Grid(H2DEF)
    cells = {}
    for n in pos:
        if n in displaced:
            continue
        cells[n] = [masters[n], cur[n][0], cur[n][1], cur[n][2]]
        occ.place(n, masters[n], cur[n][0], cur[n][1])

    def clip(r, a_, b_):
        if not (r0 <= r < r1):
            return [(a_, b_)]
        out = []
        if a_ < s0:
            out.append((a_, min(b_, s0)))
        if b_ > s1:
            out.append((max(a_, s1), b_))
        return out

    def median_point(n):
        xs, ys = [], []
        for v in cell_nets[n]:
            if len(nets[v]) > 40:
                continue
            for m_ in set(nets[v]):
                if m_ != n and m_ in cells:
                    x_, y_ = cells[m_][1] + cw[m_] / 2, cells[m_][2] + ch[m_] / 2
                    xs.append(x_); ys.append(y_)
            if v in pinxy:
                xs.append(pinxy[v][0]); ys.append(pinxy[v][1])
        if not xs:
            return pos[n][0], pos[n][1]
        return float(np.median(xs)) - cw[n] / 2, float(np.median(ys)) - ch[n] / 2
    slid = set()
    disp = []
    for n in sorted(displaced, key=lambda n: -w[n]):
        tx, ty = median_point(n)
        s_t = int(round(min(max((tx - P.X0) / P.SW, 2), 605 - w[n])))
        r_t = int(round(min(max((ty - P.Y0) / P.RH, 0), P.NR - 1)))
        if inside(r_t, s_t, w[n]):   # median inside the region: nearest outside point
            opts = [(abs(s_t - (s0 - w[n])), s0 - w[n], r_t), (abs(s1 - s_t), s1, r_t)]
            if r1 < P.NR:
                opts.append(((r1 - r_t) * 7, s_t, r1))
            if r0 > 0:
                opts.append(((r_t - r0 + 1) * 7, s_t, r0 - 1))
            _, s_t, r_t = min(opts)
            s_t = min(max(s_t, 2), 605 - w[n])
        cells[n] = [masters[n], P.X0 + s_t * P.SW, P.Y0 + r_t * P.RH, pos[n][2]]
        res = P.slide_insert(occ, cells, n, masters[n], P.X0 + s_t * P.SW, P.Y0 + r_t * P.RH, max_rows=P.NR, clip=clip)
        assert res is not None, n
        slid |= set(res[1])
        disp.append(n)
    for n in cells:
        cur[n] = [cells[n][1], cells[n][2], cells[n][3]]
    hp_legal = total_hpwl()
    # ---- 4. greedy same-width swaps inside the region
    by_w = defaultdict(list)
    for n in mem:
        by_w[w[n]].append(n)
    swaps = 0
    for it in range(passes):
        acc = 0
        for n in mem:
            tx, ty = None, None
            xs, ys = [], []
            for v in cell_nets[n]:
                if len(nets[v]) > 40:
                    continue
                for m_ in set(nets[v]):
                    if m_ != n:
                        c_ = ctr(m_); xs.append(c_[0]); ys.append(c_[1])
                if v in pinxy:
                    xs.append(pinxy[v][0]); ys.append(pinxy[v][1])
            if not xs:
                continue
            tx, ty = float(np.median(xs)), float(np.median(ys))
            cands = sorted((m_ for m_ in by_w[w[n]] if m_ != n),
                           key=lambda m_: abs(ctr(m_)[0] - tx) + abs(ctr(m_)[1] - ty))[:10]
            best = None
            for m_ in cands:
                affected = set(cell_nets[n]) | set(cell_nets[m_])
                before = sum(net_hpwl(v) for v in affected)
                cur[n], cur[m_] = cur[m_], cur[n]
                after = sum(net_hpwl(v) for v in affected)
                cur[n], cur[m_] = cur[m_], cur[n]
                if after - before < -1e-6 and (best is None or after - before < best[0]):
                    best = (after - before, m_)
            if best:
                m_ = best[1]
                cur[n], cur[m_] = cur[m_], cur[n]
                # orientation follows the row; mirror flag stays with the cell
                for z in (n, m_):
                    cur[z] = [cur[z][0], cur[z][1], orient(z, P.to_row(cur[z][1]))]
                acc += 1
        swaps += acc
        if acc == 0:
            break
    hp1 = total_hpwl()
    # ---- checks and output
    chk = P.Grid(H2DEF)
    for n in cur:
        clash = chk.place(n, masters[n], cur[n][0], cur[n][1])
        assert not clash, (n, clash)
        r = P.to_row(cur[n][1])
        assert cur[n][2] in (("N", "FN") if r % 2 == 0 else ("FS", "S")), n
    for n in mem:
        assert inside(P.to_row(cur[n][1]), P.to_site(cur[n][0]), w[n]) and \
            P.to_site(cur[n][0]) >= s0 and P.to_site(cur[n][0]) + w[n] <= s1, n
    for n in pos:
        if n not in memset:
            rr, ss = P.to_row(cur[n][1]), P.to_site(cur[n][0])
            assert not inside(rr, ss, w[n]), ("foreign cell left in region", n)
    reloc = {n: cur[n] for n in cur if cur[n] != list(pos[n])}
    json.dump(reloc, open(os.path.join(outdir, "relocate.json"), "w"), indent=0)
    area_mem = sum(cw[n] * ch[n] for n in mem)
    reg_area = (r1 - r0) * (s1 - s0) * P.SW * P.RH
    tap_area = phys[r0:r1, s0:s1].sum() * P.SW * P.RH
    dist = lambda n: abs(cur[n][0] - pos[n][0]) + abs(cur[n][1] - pos[n][1])
    rep = {"generator": "region_place.py gen2 (analytic + bisection + FFD + swaps)", "base": pdir,
           "module": module, "members": len(mem), "member_cell_area": round(area_mem, 2),
           "region_rows": [r0, r1], "region_sites": [s0, s1],
           "region_um": [round(P.X0 + s0 * P.SW, 2), round(P.Y0 + r0 * P.RH, 2), round(P.X0 + s1 * P.SW, 2),
                         round(P.Y0 + r1 * P.RH, 2)], "region_area": round(reg_area, 2),
           "tap_endcap_area_in_region": round(tap_area, 2),
           "density_D8_cells_taps": round((area_mem + tap_area) / reg_area, 4),
           "foreign_cells_displaced": len(disp), "neighbours_slid": len(slid - memset),
           "foreign_displacement_um": {"sum": round(sum(dist(n) for n in disp), 1),
                                       "max": round(max((dist(n) for n in disp), default=0), 1)},
           "slid_displacement_um_sum": round(sum(dist(n) for n in slid - memset), 1),
           "swaps": swaps, "hpwl_base_um": round(hp0, 1), "hpwl_after_legalize_um": round(hp_legal, 1),
           "hpwl_final_um": round(hp1, 1), "cells_relocated": len(reloc)}
    json.dump(rep, open(os.path.join(outdir, "relocate_report.json"), "w"), indent=1)
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
