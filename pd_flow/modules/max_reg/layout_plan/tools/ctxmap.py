#!/usr/bin/env python3
"""ctxmap.py <final.def> <netlist.v> [--json OUT]: where max_reg lives in a placed chip.
Groups: M flops (Q = core.mac.M[k]), S flops (Q = core.exponent_unit.D[k], mac_unit's S register),
the max_reg exclusive cone (cone.py definition), and the direct consumers of M outside the cone
(mac_unit's S load mux). Prints per-group centroid / bbox, per-bit M-S distance, and the HPWL of the
nets driven by the M flops and S flops (from DEF pin-less component centres)."""
import json, re, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from defparse import read_def
LIB = ("/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/"
       "gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib")
OUT = {"Z", "ZN", "Q"}
def parse(fn):
    cells = {}
    for m in re.finditer(r'gf180mcu_fd_sc_mcu7t5v0__(\w+)\s+(\S+)\s*\((.*?)\);', open(fn).read(), re.S):
        t, n, body = m.groups()
        pins = {p: net.strip().lstrip("\\").strip() for p, net in re.findall(r'\.(\w+)\s*\(\s*([^()]*?)\s*\)', body)}
        cells[n.lstrip("\\")] = (t, pins)
    return cells
def main():
    dfn, nfn = sys.argv[1:3]
    comps, nets, dbu = read_def(dfn)
    cells = parse(nfn)
    drv, loads = {}, {}
    for n, (t, pins) in cells.items():
        for p, net in pins.items():
            (drv.__setitem__(net, n) if p in OUT else loads.setdefault(net, []).append(n))
    def bitq(rx):
        d = {}
        for n, (t, p) in cells.items():
            q = p.get("Q", "")
            m = re.fullmatch(rx, q)
            if t.startswith(("dff", "sdff")) and m: d[int(m.group(1))] = n
        return d
    M = bitq(r'core\.mac\.M\[(\d+)\]'); S = bitq(r'core\.exponent_unit\.D\[(\d+)\]')
    cone = set(); stack = [cells[n][1]["D"] for n in M.values()]
    while stack:
        net = stack.pop(); c = drv.get(net)
        if c is None or c in cone: continue
        t, pins = cells[c]
        if t.startswith(("dff", "sdff", "tie")): continue
        cone.add(c); stack += [v for p, v in pins.items() if p not in OUT]
    excl = set(cone); ch = True
    mset = set(M.values())
    while ch:
        ch = False
        for c in list(excl):
            outs = [v for p, v in cells[c][1].items() if p in OUT]
            if any(l not in excl and l not in mset for o in outs for l in loads.get(o, [])):
                excl.discard(c); ch = True
    mcons = set()
    for n in M.values():
        q = cells[n][1]["Q"]
        for l in loads.get(q, []):
            if l not in excl and l not in mset: mcons.add(l)
    def pos(n):
        c = comps.get(n) or comps.get(re.sub(r'([\[\]])', r'\\\1', n))
        return (c["x"], c["y"], c["status"], c["master"]) if c else None
    def grp(name, ns):
        ps = [pos(n) for n in ns]; ps = [p for p in ps if p]
        if not ps: return {"group": name, "n": 0}
        xs = [p[0] for p in ps]; ys = [p[1] for p in ps]
        return {"group": name, "n": len(ps), "cx": round(sum(xs)/len(xs), 2), "cy": round(sum(ys)/len(ys), 2),
                "bbox": [min(xs), min(ys), max(xs), max(ys)], "status": sorted({p[2] for p in ps})}
    res = {"def": dfn, "netlist": nfn, "groups": [grp("M_flops", M.values()), grp("S_flops", S.values()),
           grp("maxreg_excl_cone", excl), grp("M_consumers_outside", mcons)],
           "excl_cells": len(excl), "M_consumers_outside": len(mcons)}
    per = []
    for k in range(22):
        pm, ps = pos(M[k]), pos(S[k])
        per.append({"bit": k, "M": M[k], "M_xy": pm[:2], "S": S[k], "S_xy": ps[:2],
                    "dist_manhattan": round(abs(pm[0]-ps[0]) + abs(pm[1]-ps[1]), 2)})
    res["per_bit"] = per
    res["mean_M_S_dist"] = round(sum(p["dist_manhattan"] for p in per) / 22, 2)
    def hpwl(net):
        ns = [drv.get(net)] + loads.get(net, [])
        ps = [pos(n) for n in ns if n]; ps = [p for p in ps if p]
        if len(ps) < 2: return 0.0
        return (max(p[0] for p in ps) - min(p[0] for p in ps)) + (max(p[1] for p in ps) - min(p[1] for p in ps))
    res["hpwl_M_q_nets"] = round(sum(hpwl(cells[n][1]["Q"]) for n in M.values()), 1)
    res["hpwl_S_q_nets"] = round(sum(hpwl(cells[n][1]["Q"]) for n in S.values()), 1)
    res["hpwl_M_d_nets"] = round(sum(hpwl(cells[n][1]["D"]) for n in M.values()), 1)
    allc = set(excl) | mset
    res["hpwl_cone_internal_nets"] = round(sum(hpwl(v) for c in excl for p, v in cells[c][1].items() if p in OUT), 1)
    js = json.dumps(res, indent=1)
    if "--json" in sys.argv: open(sys.argv[sys.argv.index("--json") + 1], "w").write(js)
    for g in res["groups"]: print(g)
    print("mean M-S dist", res["mean_M_S_dist"], "hpwl Mq", res["hpwl_M_q_nets"], "Sq", res["hpwl_S_q_nets"],
          "Md", res["hpwl_M_d_nets"], "cone", res["hpwl_cone_internal_nets"])
    for p in per: print(p["bit"], p["M"], p["M_xy"], p["S"], p["S_xy"], p["dist_manhattan"])
main()
