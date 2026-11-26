#!/usr/bin/env python3
"""chip_place.py <base_pilot_dir> <attribution.json> <floorplan_dir> <out_dir> [--iters K] [--passes N]

Whole-chip assembly generator (gen3): every instance of <base_pilot_dir>/pilot.v is placed inside the
region of its cluster (floorplan.py: labels, CLUSTER map, regions in <floorplan_dir>/floorplan.json).
  1. analytic: quadratic clique-model wirelength (nets <= 40 pins, clk skipped) with the TT pins as
     anchors, iterated K times with pseudo-anchor springs (growing weight) to each cell's spread target;
  2. spreading: per region, recursive bisection over free-site capacity (taps/endcaps excluded);
  3. legalization: per region, first-fit-decreasing into (row, tap-segment) bins nearest the targets,
     each bin ordered by target x with its slack spread evenly;
  4. improvement: greedy same-width swaps within a region that lower HPWL (N passes).
Writes <out_dir>/relocate.json (every instance) and <out_dir>/relocate_report.json.
"""
import json, os, re, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
import pdlib, placelib as P
import floorplan as F
import region_pack as RP


def main():
    a = sys.argv[1:]
    iters, passes = 5, 6
    single = "--single" in a     # control: one region = whole core (no segregation)
    if single:
        a.remove("--single")
    for flag in ("--iters", "--passes"):
        if flag in a:
            i = a.index(flag)
            v = int(a[i + 1])
            del a[i:i + 2]
            if flag == "--iters":
                iters = v
            else:
                passes = v
    pdir, attr, fpdir, outdir = a
    os.makedirs(outdir, exist_ok=True)
    inst, lab, L = F.labels(pdir, attr)
    masters, pos = RP.load_base(pdir)
    fp = json.load(open(os.path.join(fpdir, "floorplan.json")))
    regs = {r["region"]: (r["rows"][0], r["rows"][1], r["sites"][0], r["sites"][1]) for r in fp["regions"]
            if not r["region"].startswith("SPARE")}
    reg_of = {n: F.cluster_of(lab[n]) for n in inst}
    if single:
        regs = {"CORE": (0, P.NR, 2, 605)}
        reg_of = {n: "CORE" for n in inst}
    G = P.Grid(F.H2DEF)
    w = {n: G.width_sites(masters[n]) for n in masters}
    cw = {n: L[masters[n]]["w"] for n in masters}
    ch = {n: L[masters[n]]["h"] for n in masters}
    D = pdlib.parse_def(F.H2DEF, want_routes=False)
    nets = defaultdict(list)
    for n, (m, pins) in inst.items():
        for p, v in pins.items():
            if v and v != "clk" and not v.startswith("1'b"):
                nets[v].append(n)
    nets = {v: sorted(set(ns)) for v, ns in nets.items()}
    pinxy = {v: (D["pins"][v]["x"], D["pins"][v]["y"]) for v in nets if v in D["pins"]}
    cell_nets = defaultdict(list)
    for v, ns in nets.items():
        for n in ns:
            cell_nets[n].append(v)
    names = sorted(inst)
    idx = {n: k for k, n in enumerate(names)}
    N = len(names)
    cur = {n: [pos[n][0], pos[n][1], pos[n][2]] for n in names}

    def ctr(n):
        return cur[n][0] + cw[n] / 2, cur[n][1] + ch[n] / 2

    def net_hpwl(v):
        pts = [ctr(n) for n in nets[v]]
        if v in pinxy:
            pts.append(pinxy[v])
        if len(pts) < 2:
            return 0.0
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return max(xs) - min(xs) + max(ys) - min(ys)

    def hpwl_by():
        by = defaultdict(float)
        for v in nets:
            by["|".join(sorted({F.cluster_of(lab[n]) for n in nets[v]}))] += net_hpwl(v)
        return sum(by.values()), by
    hp0, by0 = hpwl_by()
    cl = {n: F.cluster_of(lab[n]) for n in inst}
    # ---- Laplacian (fixed part)
    A0 = np.zeros((N, N))
    bx0, by_0 = np.zeros(N), np.zeros(N)
    for v, ns in nets.items():
        k = len(ns) + (1 if v in pinxy else 0)
        if k < 2 or k > 40:
            continue
        wt = 2.0 / k
        mv = [idx[n] for n in ns]
        for ii, p in enumerate(mv):
            for q in mv[ii + 1:]:
                A0[p, p] += wt; A0[q, q] += wt; A0[p, q] -= wt; A0[q, p] -= wt
            if v in pinxy:
                A0[p, p] += wt; bx0[p] += wt * pinxy[v][0]; by_0[p] += wt * pinxy[v][1]
    rc = {g: (P.X0 + (r[2] + r[3]) / 2 * P.SW, P.Y0 + (r[0] + r[1]) / 2 * P.RH) for g, r in regs.items()}
    phys = np.array([[G.occ[r][s] is not None for s in range(P.NS)] for r in range(P.NR)])
    capm = (~phys).astype(int)

    def cap(ra, rb, sa, sb):
        return int(capm[ra:rb, sa:sb].sum())

    def spread(ana):
        tgt = {}

        def bisect(cells, ra, rb, sa, sb):
            if not cells:
                return
            if (rb - ra == 1 and (sb - sa) <= 40) or len(cells) == 1:
                for n in cells:
                    tgt[n] = ((sa + sb) / 2 - w[n] / 2, ra + (rb - ra - 1) / 2)
                return
            horiz = ((sb - sa) * P.SW >= (rb - ra) * P.RH and sb - sa >= 2) or rb - ra < 2
            if horiz:
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
            while k < len(order) and acc + w[order[k]] / 2 <= area * c1 / max(1, c1 + c2):
                acc += w[order[k]]
                k += 1
            if horiz:
                bisect(order[:k], ra, rb, sa, m); bisect(order[k:], ra, rb, m, sb)
            else:
                bisect(order[:k], ra, m, sa, sb); bisect(order[k:], m, rb, sa, sb)
        for g, (r0, r1, s0, s1) in regs.items():
            bisect([n for n in names if reg_of[n] == g], r0, r1, s0, s1)
        return {n: (P.X0 + (tgt[n][0] + w[n] / 2) * P.SW, P.Y0 + (tgt[n][1] + 0.5) * P.RH) for n in names}, tgt
    # ---- iterate: solve, spread, add pseudo-anchors
    anchor = {n: rc[reg_of[n]] for n in names}
    alphas = [0.02 * (3 ** k) for k in range(iters)]
    hist = []
    for k, al in enumerate([0.01] + alphas):
        A = A0.copy()
        bx, by = bx0.copy(), by_0.copy()
        for n in names:
            p = idx[n]
            A[p, p] += al; bx[p] += al * anchor[n][0]; by[p] += al * anchor[n][1]
        X, Y = np.linalg.solve(A, bx), np.linalg.solve(A, by)
        ana = {n: (X[idx[n]], Y[idx[n]]) for n in names}
        anchor, tgt = spread(ana)
        hist.append(al)
    # ---- FFD per region
    def orient(n, r):
        o = P.row_orient(r)
        return {"N": "FN", "FS": "S"}[o] if pos[n][2] in ("FN", "S") else o
    for g, (r0, r1, s0, s1) in regs.items():
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
        members = [n for n in names if reg_of[n] == g]
        for n in sorted(members, key=lambda n: (-w[n], tgt[n][1], tgt[n][0])):
            best = None
            for kk, (r, a_, b_) in enumerate(bins):
                if rem[kk] < w[n]:
                    continue
                c = abs(min(max(tgt[n][0], a_), b_ - w[n]) - tgt[n][0]) + abs(r - tgt[n][1]) * (P.RH / P.SW)
                if best is None or c < best[0]:
                    best = (c, kk)
            assert best, ("region too small", g, n)
            content[best[1]].append(n)
            rem[best[1]] -= w[n]
        for kk, (r, a_, b_) in enumerate(bins):
            cs = sorted(content[kk], key=lambda n: tgt[n][0])
            slack = (b_ - a_) - sum(w[n] for n in cs)
            x = a_
            for j, n in enumerate(cs):
                x += slack * (j + 1) // (len(cs) + 1) - slack * j // (len(cs) + 1)
                cur[n] = [P.X0 + x * P.SW, P.Y0 + r * P.RH, orient(n, r)]
                x += w[n]
            assert x <= b_
    hp_legal, _ = hpwl_by()
    # ---- swaps within region, same width
    groups = defaultdict(list)
    for n in names:
        groups[(reg_of[n], w[n])].append(n)
    swaps = 0
    for it in range(passes):
        acc = 0
        for n in names:
            xs, ys = [], []
            for v in cell_nets[n]:
                if len(nets[v]) > 40:
                    continue
                for m_ in nets[v]:
                    if m_ != n:
                        c_ = ctr(m_); xs.append(c_[0]); ys.append(c_[1])
                if v in pinxy:
                    xs.append(pinxy[v][0]); ys.append(pinxy[v][1])
            if not xs:
                continue
            tx, ty = float(np.median(xs)), float(np.median(ys))
            cands = sorted((m_ for m_ in groups[(reg_of[n], w[n])] if m_ != n),
                           key=lambda m_: abs(ctr(m_)[0] - tx) + abs(ctr(m_)[1] - ty))[:10]
            best = None
            for m_ in cands:
                aff = set(cell_nets[n]) | set(cell_nets[m_])
                before = sum(net_hpwl(v) for v in aff)
                cur[n], cur[m_] = cur[m_], cur[n]
                after = sum(net_hpwl(v) for v in aff)
                cur[n], cur[m_] = cur[m_], cur[n]
                if after - before < -1e-6 and (best is None or after - before < best[0]):
                    best = (after - before, m_)
            if best:
                m_ = best[1]
                cur[n], cur[m_] = cur[m_], cur[n]
                for z in (n, m_):
                    cur[z] = [cur[z][0], cur[z][1], orient(z, P.to_row(cur[z][1]))]
                acc += 1
        swaps += acc
        if acc == 0:
            break
    hp1, by1 = hpwl_by()
    # ---- checks
    chk = P.Grid(F.H2DEF)
    for n in names:
        assert not chk.place(n, masters[n], cur[n][0], cur[n][1]), n
        r = P.to_row(cur[n][1])
        assert cur[n][2] in (("N", "FN") if r % 2 == 0 else ("FS", "S")), n
        r0, r1, s0, s1 = regs[reg_of[n]]
        s = P.to_site(cur[n][0])
        assert r0 <= r < r1 and s0 <= s and s + w[n] <= s1, (n, reg_of[n])
    json.dump({n: cur[n] for n in names}, open(os.path.join(outdir, "relocate.json"), "w"), indent=0)
    dens = {}
    for g, (r0, r1, s0, s1) in regs.items():
        ar = (r1 - r0) * (s1 - s0) * P.SW * P.RH
        dens[g] = round((sum(cw[n] * ch[n] for n in names if reg_of[n] == g) + phys[r0:r1, s0:s1].sum() * P.SW * P.RH) / ar, 4)
    rep = {"generator": "chip_place.py gen3 (iterated quadratic + bisection + FFD + swaps, all regions)",
           "base": pdir, "floorplan": fpdir, "iters": iters, "alphas": hist, "swap_passes": passes, "swaps": swaps,
           "region_density_D8_cells_taps_before_CTS": dens,
           "hpwl_base_um": round(hp0, 1), "hpwl_after_legalize_um": round(hp_legal, 1), "hpwl_final_um": round(hp1, 1),
           "hpwl_by_cluster_set_base": {k: round(v, 1) for k, v in sorted(by0.items(), key=lambda t: -t[1])},
           "hpwl_by_cluster_set_final": {k: round(v, 1) for k, v in sorted(by1.items(), key=lambda t: -t[1])}}
    json.dump(rep, open(os.path.join(outdir, "relocate_report.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in rep.items() if not k.startswith("hpwl_by")}, indent=1))
    print(json.dumps({k: (rep["hpwl_by_cluster_set_base"].get(k), v) for k, v in rep["hpwl_by_cluster_set_final"].items()}))


if __name__ == "__main__":
    main()
