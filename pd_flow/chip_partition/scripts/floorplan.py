#!/usr/bin/env python3
"""floorplan.py <pilot_dir> <attribution.json> <outdir> [density]

Chip floorplan for the all-custom-placed TT 1x1 GF180 tile (Architect A, pd_flow/chip_partition).
Two bands of rows: bottom band B (rows 0..31) holds MAC-C (west) and DIV (east); top band T
(rows 32..38, under the TT pins) holds CTRL (west/middle, under the flash pins) and FE (east, under
the SPI/clk/rst_n/ena pins). Each region is the smallest rectangle (whole sites and rows) whose D8
density (cells + taps/endcaps inside / region area) stays <= density (default 0.90), holding:
  module cells at h2 final masters (every instance of <pilot_dir>/pilot.v, labelled in context:
  attribution module_of_cell; repair buffers inherit their upstream module; shared cells as mapped
  below) + a CTS reserve (h2 clock tree 851.74 um2 split by flop count) + the tie reserve (h2 ties,
  re-created by repair_tie_fanout next to the constant pins on the top edge, so booked to band T).
Everything left over is listed as spare (free area). Also: TT pin check, cut nets per region pair with
their order along the shared boundary (from h2 coordinates), slivers left in tap segments by each
boundary. Writes <outdir>/regions.json (for svg_modules.py/region_pack.py), floorplan.json, budget.md.
"""
import json, os, re, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(__file__))
import pdlib, placelib as P

H2DEF = "/Users/samuelzhang/ttharden/fx_h2_k6/runs/wokwi/final/def/tt_um_attention_head_gf.def"
REP = re.compile(r"^(fanout|load_slew|wire|rebuffer|split|max_cap|max_length)\d+")
CLUSTER = {"MAC": "MAC-C", "MAX": "MAC-C", "EXP": "MAC-C", "shared:MAC+MAX": "MAC-C", "shared:FE+MAC": "MAC-C",
           "shared:DIV+MAC": "MAC-C", "DIV": "DIV", "CTRL": "CTRL", "shared:CTRL+DIV": "CTRL",
           "shared:CTRL+MAC": "CTRL", "shared:CTRL+MAX": "CTRL", "shared:CTRL+MAC+MAX": "CTRL",
           "shared:CTRL+FE": "CTRL", "FE": "FE", "tie:new": "CTRL", "port:out": "CTRL"}
FLOPS = {"MAC-C": 194 + 22, "DIV": 57, "CTRL": 41, "FE": 15}     # attribution flop groups (329 total)
H2_CLOCK_AREA, H2_CLOCK_CELLS = 851.74, 31


def labels(pdir, attr):
    mod = json.load(open(attr))["module_of_cell"]
    txt = open(os.path.join(pdir, "pilot.v")).read()
    L = pdlib.lef_macros()
    inst = {}
    drv = {}
    for m, n, body in re.findall(r"^\s*(gf180mcu_fd_sc_mcu7t5v0__\w+)\s+(\S+)\s*\((.*?)\);", txt, re.M | re.S):
        n = n.replace("\\", "")
        pins = dict((p, v.replace("\\", "").strip()) for p, v in re.findall(r"\.(\w+)\s*\(\s*([^()]*?)\s*\)", body))
        inst[n] = (m, pins)
        for p, v in pins.items():
            if L[m]["dir"].get(p) == "OUTPUT":
                drv[v] = n

    def up(n, k=0):
        if n in mod and not REP.match(n):
            return mod[n]
        m, pins = inst[n]
        ins = [v for p, v in pins.items() if L[m]["dir"].get(p) == "INPUT"]
        d = drv.get(ins[0]) if ins else None
        return up(d, k + 1) if d and k < 12 else "PI"
    lab = {}
    po = re.compile(r"^(uo_out|uio_out|uio_oe)\[\d\]$")
    for n, (m, pins) in inst.items():
        if re.search(r"__tie[hl]$", m):
            lab[n] = "tie:new"
        elif any(po.match(v) and L[m]["dir"].get(p) == "OUTPUT" for p, v in pins.items()):
            lab[n] = "port:out"   # output-port buffer: belongs under its pin on the top edge
        elif REP.match(n):
            lab[n] = "repair:" + up(n)
        else:
            lab[n] = mod.get(n, "?")
    return inst, lab, L


def cluster_of(label):
    return CLUSTER.get(label.replace("repair:", ""), "?")


def main():
    pdir, attr, outdir = sys.argv[1:4]
    dens = float(sys.argv[4]) if len(sys.argv) > 4 else 0.90
    os.makedirs(outdir, exist_ok=True)
    inst, lab, L = labels(pdir, attr)
    assert "?" not in {cluster_of(l) for l in lab.values()}, Counter(l for l in lab.values() if cluster_of(l) == "?")
    area = lambda n: L[inst[n][0]]["w"] * L[inst[n][0]]["h"]
    budget = defaultdict(float)
    by_label = defaultdict(float)
    for n in inst:
        budget[cluster_of(lab[n])] += area(n)
        by_label[lab[n]] += area(n)
    cts = {c: H2_CLOCK_AREA * f / sum(FLOPS.values()) for c, f in FLOPS.items()}
    G = P.Grid(H2DEF)
    import numpy as np
    phys = np.array([[G.occ[r][s] is not None for s in range(P.NS)] for r in range(P.NR)])
    cell_um2 = P.SW * P.RH

    def rect_stats(r0, r1, s0, s1):
        a = (r1 - r0) * (s1 - s0) * cell_um2
        t = phys[r0:r1, s0:s1].sum() * cell_um2
        return a, t

    def min_width(need, r0, r1, anchor, side):
        """smallest width (sites) from anchor growing to `side` (+1 east, -1 west) with D8 <= dens"""
        for w in range(1, P.NS):
            s0, s1 = (anchor, anchor + w) if side > 0 else (anchor - w, anchor)
            if s0 < 0 or s1 > P.NS:
                break
            a, t = rect_stats(r0, r1, s0, s1)
            if (need + t) / a <= dens:
                return s0, s1
        raise SystemExit(f"does not fit: need {need}")
    need = {c: budget[c] + cts.get(c, 0) for c in budget}

    def snap(r0, r1, s0, s1, inner_is_s0):
        def bad(edge):
            k = 0
            for r in range(r0, r1):
                for a_, b_ in P.segments(G, r):
                    if a_ < edge < b_ and min(edge - a_, b_ - edge) < 4:
                        k += 1
            return k
        best = None
        for d in range(0, 9):
            e = (s0 - d) if inner_is_s0 else (s1 + d)
            if not 2 <= e <= 605:
                continue
            c = (bad(e), d)
            if best is None or c < best[0]:
                best = (c, e)
        e = best[1]
        return (r0, r1, e, s1) if inner_is_s0 else (r0, r1, s0, e)
    B, T = (0, 32), (32, 39)
    regs = {}
    regs["MAC-C"] = snap(*((B[0], B[1]) + min_width(need["MAC-C"], *B, 2, +1)), False)
    regs["DIV"] = snap(*((B[0], B[1]) + min_width(need["DIV"], *B, 605, -1)), True)
    regs["FE"] = snap(*((T[0], T[1]) + min_width(need["FE"], *T, 605, -1)), True)
    regs["CTRL"] = snap(*((T[0], T[1]) + min_width(need["CTRL"], *T, regs["FE"][2], -1)), True)
    assert regs["MAC-C"][3] <= regs["DIV"][2] and regs["CTRL"][2] >= 2
    spare = {"SPARE-B": (B[0], B[1], regs["MAC-C"][3], regs["DIV"][2]),
             "SPARE-T": (T[0], T[1], 2, regs["CTRL"][2])}
    # ---- table
    rows_out = []
    for name, (r0, r1, s0, s1) in list(regs.items()) + list(spare.items()):
        a, t = rect_stats(r0, r1, s0, s1)
        cells = budget.get(name, 0.0)
        c = cts.get(name, 0.0)
        rows_out.append({"region": name, "rows": [r0, r1], "sites": [s0, s1],
                         "rect_um": [round(P.X0 + s0 * P.SW, 2), round(P.Y0 + r0 * P.RH, 2),
                                     round(P.X0 + s1 * P.SW, 2), round(P.Y0 + r1 * P.RH, 2)],
                         "area": round(a, 2), "tap_area": round(t, 2), "cells_h2_masters": round(cells, 2),
                         "cts_reserve": round(c, 2), "d8_density": round((cells + c + t) / a, 4) if a else 0,
                         "free": round(a - cells - c - t, 2)})
    core = P.NS * P.NR * cell_um2
    endcap_left_right = phys[:, :2].sum() * cell_um2 + phys[:, 605:].sum() * cell_um2
    tot = {"core": round(core, 2), "regions": round(sum(r["area"] for r in rows_out), 2),
           "endcap_columns": round(endcap_left_right, 2),
           "cells": round(sum(budget.values()), 2), "cts_reserve": round(sum(cts.values()), 2),
           "taps_endcaps": round(phys.sum() * cell_um2, 2)}
    tot["free_total"] = round(core - tot["cells"] - tot["cts_reserve"] - tot["taps_endcaps"], 2)
    tot["chip_d8"] = round((tot["cells"] + tot["cts_reserve"] + tot["taps_endcaps"]) / core, 4)
    # ---- slivers: tap-segment pieces cut off by each vertical region boundary
    slivers = {}
    for name, (r0, r1, s0, s1) in regs.items():
        sl = Counter()
        for r in range(r0, r1):
            for a_, b_ in P.segments(G, r):
                for edge in (s0, s1):
                    if a_ < edge < b_:
                        sl[min(edge - a_, b_ - edge)] += 1
        slivers[name] = dict(sorted(sl.items()))
    # ---- pins
    D = pdlib.parse_def(H2DEF, want_routes=False)
    pin_use = defaultdict(Counter)
    for n, (m, pins) in inst.items():
        for p, v in pins.items():
            base = re.sub(r"\[\d+\]$", "", v)
            if v in D["pins"] or base in ("ui_in", "uo_out", "uio_in", "uio_out", "uio_oe", "clk", "rst_n", "ena"):
                pin_use[v][cluster_of(lab[n])] += 1
    pin_check = []
    for pn, uses in sorted(pin_use.items(), key=lambda t: -D["pins"].get(t[0], {"x": 0})["x"]):
        if pn not in D["pins"]:
            continue
        x = D["pins"][pn]["x"]
        for c, k in uses.items():
            if pn == "clk":
                continue
            r0, r1, s0, s1 = regs[c]
            x0, x1 = P.X0 + s0 * P.SW, P.X0 + s1 * P.SW
            top = r1 == P.NR
            d = 0 if x0 <= x <= x1 else min(abs(x - x0), abs(x - x1))
            pin_check.append({"pin": pn, "x": x, "region": c, "loads_or_drivers": k, "region_on_top_edge": top,
                              "x_inside_region_span": d == 0, "x_dist_um": round(d, 2),
                              "y_dist_um": round(0 if top else 160.22 - (P.Y0 + r1 * P.RH), 2)})
    # ---- cut nets between regions, ordered along the shared boundary (h2 pin coordinates)
    comps = D["comps"]
    net_pins = defaultdict(list)
    for n, (m, pins) in inst.items():
        for p, v in pins.items():
            if v and v not in ("clk",) and not v.startswith("1'b"):
                net_pins[v].append(n)
    cuts = defaultdict(list)
    for v, ns in net_pins.items():
        cs = sorted({cluster_of(lab[n]) for n in ns})
        if len(cs) < 2:
            continue
        xs = [comps[n]["x"] for n in ns if n in comps and comps[n]["x"] is not None]
        ys = [comps[n]["y"] for n in ns if n in comps and comps[n]["y"] is not None]
        cuts["|".join(cs)].append((v, round(sum(xs) / len(xs), 1) if xs else None, round(sum(ys) / len(ys), 1) if ys else None))

    def side(a, b):
        ra, rb = regs[a], regs[b]
        if ra[0] == rb[0]:   # same band: vertical boundary, order along y
            return ("east" if ra[2] < rb[2] else "west"), 2
        return ("north" if ra[0] < rb[0] else "south"), 1
    ports = {}
    for k, lst in sorted(cuts.items(), key=lambda t: -len(t[1])):
        cs = k.split("|")
        if len(cs) == 2:
            sd, axis = side(cs[0], cs[1])
            order = [v for v, x, y in sorted(lst, key=lambda t: (t[axis] if t[axis] is not None else 0))]
            ports[k] = {"nets": len(lst), "side_of_" + cs[0]: sd, "order_axis": "y" if axis == 2 else "x",
                        "order": order}
        else:
            ports[k] = {"nets": len(lst), "multi_region": True, "order": [v for v, _, _ in lst]}
    out = {"inputs": {"pilot_dir": pdir, "pilot_v_sha256": pdlib.sha(os.path.join(pdir, "pilot.v"), 64),
                      "attribution": attr, "h2_def": H2DEF}, "density_target": dens,
           "budget_by_label": {k: round(v, 2) for k, v in sorted(by_label.items(), key=lambda t: -t[1])},
           "cts_reserve": {k: round(v, 2) for k, v in cts.items()}, "regions": rows_out, "totals": tot,
           "slivers_sites_count": slivers, "pins": pin_check, "ports": ports}
    json.dump(out, open(os.path.join(outdir, "floorplan.json"), "w"), indent=1)
    json.dump({"regions": [{"name": r["region"], "rect": r["rect_um"], "rows": r["rows"], "sites": r["sites"]}
                           for r in rows_out]}, open(os.path.join(outdir, "regions.json"), "w"), indent=1)
    md = ["| Region | rows | sites | x0-x1 um | y0-y1 um | area um2 | taps um2 | cells um2 | CTS reserve | D8 | free um2 |",
          "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for r in rows_out:
        x0, y0, x1, y1 = r["rect_um"]
        md.append(f"| {r['region']} | {r['rows'][0]}-{r['rows'][1]-1} | {r['sites'][0]}-{r['sites'][1]-1} | "
                  f"{x0:.2f}-{x1:.2f} | {y0:.2f}-{y1:.2f} | {r['area']:,.1f} | {r['tap_area']:,.1f} | "
                  f"{r['cells_h2_masters']:,.1f} | {r['cts_reserve']:,.1f} | {r['d8_density']:.3f} | {r['free']:,.1f} |")
    md.append(f"| endcap columns | 0-38 | 0-1, 605-606 | | | {tot['endcap_columns']:,.1f} | {tot['endcap_columns']:,.1f} | | | | 0 |")
    md.append(f"| **core** | | | | | **{tot['core']:,.1f}** | {tot['taps_endcaps']:,.1f} | {tot['cells']:,.1f} | "
              f"{tot['cts_reserve']:,.1f} | {tot['chip_d8']:.3f} | **{tot['free_total']:,.1f}** |")
    open(os.path.join(outdir, "budget.md"), "w").write("\n".join(md) + "\n")
    print("\n".join(md))
    print(json.dumps(slivers))
    for pc in pin_check:
        if not pc["x_inside_region_span"] or not pc["region_on_top_edge"]:
            print("PIN-OFFSET", pc)
    for k, v in list(ports.items())[:14]:
        print(k, v["nets"], {kk: vv for kk, vv in v.items() if kk not in ("order", "nets")})


if __name__ == "__main__":
    main()
