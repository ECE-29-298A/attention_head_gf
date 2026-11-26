#!/usr/bin/env python3
"""region_pack.py <base_pilot_dir> <attribution.json> <module> <density> <out_relocate.json> [--rect r0,r1,s0,s1]

Compacts every cell of one in-context module (plus the repair buffers its nets carry) into ONE
rectangular region of the 1x1 core at a target packing density (D8: cell area + tap/endcap area
inside the region, over the region area, region on whole sites and rows), keeping every other
cell where the base placement has it, except foreign cells inside the region, which move to the
nearest free gap outside it.

Region choice (unless --rect): over heights H in {10,13,16,20,26,39} rows, every row offset and
every 2-site column offset, the smallest-width rectangle that reaches the density with the module's
cell area, minimising (foreign cell area inside) + (module cell area outside) = area that must move.
Packing: module cells keep their relative order. Targets are an affine map of their base positions
(5..95 percentile box) into the region. Rows are filled bottom-up in target-y order to equal
fill, and each row is packed in target-x order with its whitespace spread evenly, skipping taps.
Output: {inst: [x, y, orient]} for make_pilot.py --relocate, plus a report.
"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(__file__))
import pdlib, placelib as P

REP = re.compile(r"^(fanout|load_slew|wire|rebuffer|split|max_cap|max_length)\d+")


def load_base(pdir):
    masters = {n.replace("\\", ""): m for m, n in
               re.findall(r"^\s*(gf180mcu_fd_sc_mcu7t5v0__\w+)\s+(\S+)\s*\(", open(os.path.join(pdir, "pilot.v")).read(), re.M)}
    pos = {}
    for line in open(os.path.join(pdir, "placement.cfg")):
        t = line.split()
        if t:
            pos[t[0]] = [float(t[1]), float(t[2]), t[3]]
    return masters, pos


def module_members(pdir, attr, module, masters):
    mod = json.load(open(attr))["module_of_cell"]
    txt = open(os.path.join(pdir, "pilot.v")).read()
    inst_re = re.compile(r"^\s*(gf180mcu_fd_sc_mcu7t5v0__\w+)\s+(\S+)\s*\((.*?)\);", re.M | re.S)
    L = pdlib.lef_macros()
    drv, ins = {}, {}
    for m, n, body in inst_re.findall(txt):
        n = n.replace("\\", "")
        pins = dict(re.findall(r"\.(\w+)\s*\(\s*([^()]*?)\s*\)", body))
        ins[n] = [v for p, v in pins.items() if L[m]["dir"].get(p) == "INPUT"]
        for p, v in pins.items():
            if L[m]["dir"].get(p) == "OUTPUT":
                drv[v] = n

    def up(n, k=0):
        if n in mod:
            return mod[n]
        if k > 10 or not ins.get(n):
            return "?"
        d = drv.get(ins[n][0])
        return up(d, k + 1) if d else "PI"
    mem = [n for n in masters if mod.get(n) == module or (REP.match(n) and up(n) == module)]
    return mem


def main():
    a = sys.argv[1:]
    rect = None
    if "--rect" in a:
        i = a.index("--rect")
        rect = [int(v) for v in a[i + 1].split(",")]
        del a[i:i + 2]
    pdir, attr, module, dens, out = a[0], a[1], a[2], float(a[3]), a[4]
    masters, pos = load_base(pdir)
    ref_def = "/Users/samuelzhang/ttharden/fx_h2_k6/runs/wokwi/final/def/tt_um_attention_head_gf.def"
    G = P.Grid(ref_def)
    L = pdlib.lef_macros()
    mem = set(module_members(pdir, attr, module, masters))
    wsites = {n: G.width_sites(masters[n]) for n in masters}
    cell_sites_mem = sum(wsites[n] for n in mem)
    # per-site maps (rows x sites): fixed physical occupancy, base occupancy by member / foreign
    import numpy as np
    phys = np.zeros((P.NR, P.NS), bool)
    for r in range(P.NR):
        for s in range(P.NS):
            phys[r, s] = G.occ[r][s] is not None
    foreign = np.zeros((P.NR, P.NS), float)
    member = np.zeros((P.NR, P.NS), float)
    for n, (x, y, o) in pos.items():
        r, s = P.to_row(y), P.to_site(x)
        (member if n in mem else foreign)[r, s:s + wsites[n]] += 1
    cp = lambda M: np.pad(M.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    Cphys, Cfor, Cmem = cp(phys.astype(float)), cp(foreign), cp(member)
    box = lambda C, r0, r1, s0, s1: C[r1, s1] - C[r0, s1] - C[r1, s0] + C[r0, s0]
    best = None
    if rect:
        cands = [tuple(rect)]
    else:
        cands = []
        for H in (10, 13, 16, 20, 26, 39):
            for r0 in range(0, P.NR - H + 1):
                r1 = r0 + H
                for s0 in range(0, P.NS, 2):
                    # smallest width reaching the density
                    for W in range(int(cell_sites_mem / H / dens) - 2, P.NS - s0 + 1):
                        s1 = s0 + W
                        if s1 > P.NS:
                            break
                        tot = H * W
                        ph = box(Cphys, r0, r1, s0, s1)
                        if (cell_sites_mem + ph) / tot <= dens + 1e-9 and tot - ph >= cell_sites_mem:
                            cands.append((r0, r1, s0, s1))
                            break
    for (r0, r1, s0, s1) in cands:
        moved = box(Cfor, r0, r1, s0, s1) + (cell_sites_mem - box(Cmem, r0, r1, s0, s1))
        if best is None or moved < best[0]:
            best = (moved, (r0, r1, s0, s1))
    moved_sites, (r0, r1, s0, s1) = best
    def try_pack(r0, r1, s0, s1):
        H, W = r1 - r0, s1 - s0
        # --- pack members into the region
        xs = sorted(pos[n][0] for n in mem)
        ys = sorted(pos[n][1] for n in mem)
        q = lambda v, f: v[min(len(v) - 1, int(f * len(v)))]
        bx0, bx1, by0, by1 = q(xs, .05), q(xs, .95), q(ys, .05), q(ys, .95)
        tgt = {}
        for n in mem:
            x, y = pos[n][0], pos[n][1]
            fx = min(1, max(0, (x - bx0) / max(1e-6, bx1 - bx0)))
            fy = min(1, max(0, (y - by0) / max(1e-6, by1 - by0)))
            tgt[n] = (s0 + fx * (W - wsites[n]), r0 + fy * (H - 1))
        # segment-aware packing. Segments = maximal free (non-tap/endcap) site runs of each region row.
        def segs(r):
            out, a = [], None
            for x in range(s0, s1):
                if not phys[r, x] and a is None:
                    a = x
                if phys[r, x] and a is not None:
                    out.append((a, x)); a = None
            if a is not None:
                out.append((a, s1))
            return out
        rowsegs = [segs(r) for r in range(r0, r1)]
        cap = [sum(b - a for a, b in sg) for sg in rowsegs]
        total = sum(wsites[n] for n in mem)
        share = total / sum(cap)

        def fit(lst, sg):
            """order-preserving first fit of lst (sorted by target x) into segments; None if impossible"""
            rem = [b - a for a, b in sg]
            k, asg = 0, []
            for n in lst:
                while k < len(sg) and rem[k] < wsites[n]:
                    k += 1
                if k == len(sg):
                    return None
                asg.append(k)
                rem[k] -= wsites[n]
            return asg

        def fit_any(lst, sg):
            """first-fit-decreasing (reorders) when order-preserving fit fails"""
            rem = [b - a for a, b in sg]
            asg = {}
            for n in sorted(lst, key=lambda n: -wsites[n]):
                k = min((i for i in range(len(sg)) if rem[i] >= wsites[n]),
                        key=lambda i: abs((sg[i][0] + sg[i][1]) / 2 - tgt[n][0]), default=None)
                if k is None:
                    return None
                asg[n] = k
                rem[k] -= wsites[n]
            return [asg[n] for n in lst]
        # global first-fit-decreasing over all (row, segment) bins of the region: widest cells first
        # (29-site flops need whole tap segments), each to the bin with room that is nearest its target
        # (distance in sites; one row = RH/SW = 7 sites); then in each bin cells are ordered by target x
        # and the bin's slack is spread evenly between them.
        bins = [(i, a_, b_) for i in range(H) for a_, b_ in rowsegs[i]]
        rem = [b_ - a_ for _, a_, b_ in bins]
        content = [[] for _ in bins]
        for n in sorted(mem, key=lambda n: (-wsites[n], tgt[n][1], tgt[n][0])):
            w = wsites[n]
            tx, tr = tgt[n][0], tgt[n][1] - r0
            best_k, best_c = None, None
            for k, (i, a_, b_) in enumerate(bins):
                if rem[k] < w:
                    continue
                cx = min(max(tx, a_), b_ - w)
                c = abs(cx - tx) + abs(i - tr) * (P.RH / P.SW)
                if best_c is None or c < best_c:
                    best_k, best_c = k, c
            if best_k is None:
                return None
            content[best_k].append(n)
            rem[best_k] -= w
        reloc = {}
        for k, (i, a_, b_) in enumerate(bins):
            cs = sorted(content[k], key=lambda n: tgt[n][0])
            if not cs:
                continue
            r = r0 + i
            slack = (b_ - a_) - sum(wsites[n] for n in cs)
            x = a_
            for j, n in enumerate(cs):
                x += slack * (j + 1) // (len(cs) + 1) - slack * j // (len(cs) + 1)
                o = P.row_orient(r)
                if pos[n][2] in ("FN", "S"):
                    o = {"N": "FN", "FS": "S"}[o]
                reloc[n] = [P.X0 + x * P.SW, P.Y0 + r * P.RH, o]
                x += wsites[n]
            assert x <= b_, (r, k, x, b_)
        return reloc
    grown = 0
    while True:
        reloc = try_pack(r0, r1, s0, s1)
        if reloc is not None:
            break
        if s1 < P.NS:
            s1 += 1
        else:
            s0 -= 1
        grown += 1
        assert grown < 200
    H, W = r1 - r0, s1 - s0
    # --- foreign cells inside the region: nearest free gap outside it
    occ = P.Grid(ref_def)
    inside = lambda r, s, w: r0 <= r < r1 and s < s1 and s + w > s0
    for n, (x, y, o) in pos.items():
        if n in mem:
            continue
        r, s = P.to_row(y), P.to_site(x)
        if not inside(r, s, wsites[n]):
            occ.place(n, masters[n], x, y)
    for n, v in reloc.items():
        occ.place(n, masters[n], v[0], v[1])
    displaced = [n for n in pos if n not in mem and inside(P.to_row(pos[n][1]), P.to_site(pos[n][0]), wsites[n])]
    print('region rows', r0, r1, 'sites', s0, s1, 'grown', grown, 'displaced', len(displaced),
          'displaced sites', sum(wsites[n] for n in displaced), file=sys.stderr)
    disp_report = []
    cells = {}
    for n, (x, y, o) in pos.items():
        if n in mem or n in displaced:
            continue
        cells[n] = [masters[n], x, y, o]
    for n, v in reloc.items():
        cells[n] = [masters[n]] + list(v)

    def clip(r, a, b):
        if not (r0 <= r < r1):
            return [(a, b)]
        out = []
        if a < s0:
            out.append((a, min(b, s0)))
        if b > s1:
            out.append((max(a, s1), b))
        return out
    slid = set()
    for n in sorted(displaced, key=lambda n: -wsites[n]):
        x, y = pos[n][0], pos[n][1]
        r, s = P.to_row(y), P.to_site(x)
        # nearest point outside the region: left/right of it in the same row, or the row above/below
        opts = [(abs(s - (s0 - wsites[n])) * P.SW, P.X0 + max(0, s0 - wsites[n]) * P.SW, y),
                (abs(s - s1) * P.SW, P.X0 + min(P.NS - wsites[n], s1) * P.SW, y)]
        if r1 < P.NR:
            opts.append(((r1 - r) * P.RH, x, P.Y0 + r1 * P.RH))
        if r0 > 0:
            opts.append(((r - r0 + 1) * P.RH, x, P.Y0 + (r0 - 1) * P.RH))
        _, tx, ty = min(opts)
        cells[n] = [masters[n], tx, ty, pos[n][2]]
        res = P.slide_insert(occ, cells, n, masters[n], tx, ty, max_rows=P.NR, clip=clip)
        if res is None:
            del cells[n]
            tx2, ty2, o2, d = occ.find_spot(masters[n], x, y, forbid=lambda rr, ss, w: inside(rr, ss, w))
            o2 = {"N": "FN", "FS": "S"}[o2] if pos[n][2] in ("FN", "S") else o2
            cells[n] = [masters[n], tx2, ty2, o2]
            occ.place(n, masters[n], tx2, ty2)
            res = (d, [])
        slid |= set(res[1])
        d = abs(cells[n][1] - x) + abs(cells[n][2] - y)
        disp_report.append((n, round(d, 2)))
    for n in list(displaced) + sorted(slid):
        reloc[n] = list(cells[n][1:])
    for n in slid:
        disp_report.append((n, round(abs(cells[n][1] - pos[n][0]) + abs(cells[n][2] - pos[n][1]), 2)))
    # --- report
    A = pdlib.liberty_areas()
    area_mem = sum(L[masters[n]]["w"] * L[masters[n]]["h"] for n in mem)
    phys_area = phys[r0:r1, s0:s1].sum() * P.SW * P.RH
    reg_area = W * H * P.SW * P.RH
    rep = {"module": module, "members": len(mem), "member_cell_area": round(area_mem, 2),
           "region_rows": [r0, r1], "region_sites": [s0, s1], "columns_added_for_packability": grown,
           "region_um": [round(P.X0 + s0 * P.SW, 2), round(P.Y0 + r0 * P.RH, 2), round(P.X0 + s1 * P.SW, 2),
                         round(P.Y0 + r1 * P.RH, 2)],
           "region_area": round(reg_area, 2), "tap_endcap_area_in_region": round(phys_area, 2),
           "density_D8": round((area_mem + phys_area) / reg_area, 4), "target": dens,
           "moved_area_sites_proxy": moved_sites,
           "foreign_cells_displaced": len(displaced), "neighbours_slid": len(slid),
           "foreign_displacement_um": {"sum": round(sum(d for _, d in disp_report), 1),
                                       "max": max((d for _, d in disp_report), default=0)},
           "member_displacement_um_mean": round(sum(abs(reloc[n][0] - pos[n][0]) + abs(reloc[n][1] - pos[n][1])
                                                    for n in mem) / len(mem), 2)}
    json.dump(reloc, open(out, "w"), indent=0)
    json.dump(rep, open(out.replace(".json", "_report.json"), "w"), indent=1)
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
