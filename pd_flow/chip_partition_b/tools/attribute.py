#!/usr/bin/env python3
"""attribute.py: attribute every cell of a FLAT synthesized netlist (shipped flow, ABC across all
module boundaries) to an RTL module instance, then locate it in a placed DEF.

Method (no estimates; every label is traceable to one of three evidence classes):
  1. flop   : a flat flop is matched to a flop of the HIERARCHY-KEPT netlist through the RTL alias
              set of its Q net (Yosys `proc; flatten; opt_clean` of the golden RTL keeps every alias,
              e.g. core.exponent_unit.D[3] == core.mac.S[3] == core.score[3]). The hier flop's
              instance path is the label (exact).
  2. func   : bit-parallel random simulation (256 vectors) of both netlists from the same primary
              inputs and the same values on matched flop outputs. A flat combinational net whose
              function (or complement) is computed by cells of exactly one hier instance gets that
              label ("func-unique"); several instances -> "func-multi" (resolved in step 3 among them).
  3. nbr    : remaining cells take the majority label of their netlist neighbours (iterated to a
              fixed point). These are ABC-restructured cells with no functional twin in the
              hierarchical mapping, i.e. logic merged across or inside boundaries.
Usage: attribute.py --flat A.nl.v.json --hier B.nl.v.json --aliases rtl_flat_aliases.json
                    [--def placed.def] --out OUT.json [--svg OUT.svg]
"""
import argparse, json, os, random, re, sys
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdlib import liberty, cell_class, PFX, read_def, lef_sizes, sha

NV = 256
MASK = (1 << NV) - 1


def compile_fn(expr, inputs):
    toks = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|[()!&|^*+']|\S", expr)
    pos = [0]
    peek = lambda: toks[pos[0]] if pos[0] < len(toks) else None
    def take():
        t = toks[pos[0]]; pos[0] += 1; return t
    def unary():
        t = peek()
        if t == "!":
            take(); r = f"(M ^ {unary()})"
        elif t == "(":
            take(); v = p_or(); assert take() == ")"; r = f"({v})"
        elif t in ("0", "1"):
            take(); r = "M" if t == "1" else "0"
        else:
            n = take(); assert n in inputs, (n, expr); r = f"v[{n!r}]"
        while peek() == "'":
            take(); r = f"(M ^ {r})"
        return r
    def p_and():
        r = unary()
        while peek() in ("&", "*") or (peek() not in (None, ")", "|", "+", "^")):
            if peek() in ("&", "*"): take()
            r = f"({r} & {unary()})"
        return r
    def p_xor():
        r = p_and()
        while peek() == "^":
            take(); r = f"({r} ^ {p_and()})"
        return r
    def p_or():
        r = p_xor()
        while peek() in ("|", "+"):
            take(); r = f"({r} | {p_xor()})"
        return r
    code = p_or()
    assert pos[0] == len(toks), expr
    return eval(f"lambda v, M: {code}")


def bitname(n, i, nbits, attrs):
    if nbits == 1:
        return n
    off = int(attrs.get("offset", 0)) if isinstance(attrs, dict) else 0
    return f"{n}[{i + off}]"


def load_flat(path):
    d = json.load(open(path))
    top = [n for n, m in d["modules"].items() if m.get("attributes", {}).get("top")][0]
    m = d["modules"][top]
    cells = []
    for n, c in m["cells"].items():
        cells.append({"name": n, "type": c["type"].replace(PFX, ""), "label": None,
                      "conn": {p: list(b) for p, b in c["connections"].items()}})
    names = defaultdict(list)
    for n, v in m["netnames"].items():
        for i, b in enumerate(v["bits"]):
            if isinstance(b, int):
                names[b].append(bitname(n, i, len(v["bits"]), v))
    ports = {n: (p["direction"], list(p["bits"])) for n, p in m["ports"].items()}
    return {"top": top, "cells": cells, "names": names, "ports": ports}


def load_hier_flattened(path):
    d = json.load(open(path))
    mods = d["modules"]
    top = [n for n, m in mods.items() if m.get("attributes", {}).get("top")][0]
    cells, names = [], defaultdict(list)
    nid = [10 ** 7]
    def walk(mn, path, pmap):
        m = mods[mn]
        local = dict(pmap)
        def g(b):
            if not isinstance(b, int): return b
            if b not in local:
                nid[0] += 1; local[b] = nid[0]
            return local[b]
        pre = (path + ".") if path else ""
        for n, v in m["netnames"].items():
            for i, b in enumerate(v["bits"]):
                if isinstance(b, int):
                    names[g(b)].append(pre + bitname(n, i, len(v["bits"]), v))
        for cn, c in m["cells"].items():
            t = c["type"]
            if t.startswith(PFX):
                cells.append({"name": pre + cn, "type": t.replace(PFX, ""), "label": path or "top",
                              "conn": {p: [g(b) for b in bits] for p, bits in c["connections"].items()}})
            else:
                sub = mods[t]
                cmap = {}
                for pn, pv in sub["ports"].items():
                    for i, b in enumerate(pv["bits"]):
                        cmap[b] = g(c["connections"][pn][i])
                walk(t, pre + cn, cmap)
    tm = mods[top]
    pmap = {}
    for pn, pv in tm["ports"].items():
        for b in pv["bits"]:
            pmap[b] = b
    walk(top, "", pmap)
    ports = {n: (p["direction"], list(p["bits"])) for n, p in tm["ports"].items()}
    return {"top": top, "cells": cells, "names": names, "ports": ports}


class Sim:
    def __init__(self, nl, lib):
        self.nl, self.lib = nl, lib
        self.fn = {}
        for c in nl["cells"]:
            t = c["type"]
            if t in self.fn: continue
            L = lib[t]
            ins = [p for p, x in L["pins"].items() if x["dir"] == "input"]
            outs = {}
            for p, x in L["pins"].items():
                if x["dir"] == "output":
                    f = x["function"]
                    if L["ff"] or L["latch"]:
                        outs[p] = None
                    elif f is None:
                        raise SystemExit(f"no function for {t}.{p}")
                    else:
                        outs[p] = compile_fn(f, ins)
            self.fn[t] = (ins, outs)
        self.drv = {}
        for i, c in enumerate(nl["cells"]):
            ins, outs = self.fn[c["type"]]
            for p in outs:
                for b in c["conn"].get(p, []):
                    if isinstance(b, int):
                        self.drv[b] = (i, p)
        # topological order of combinational cells (iterative DFS)
        self.seq = [i for i, c in enumerate(nl["cells"]) if lib[c["type"]]["ff"] or lib[c["type"]]["latch"]]
        order, state = [], {}
        for s in range(len(nl["cells"])):
            if s in state or s in self.seq: continue
            stack = [(s, 0)]
            while stack:
                i, k = stack.pop()
                if k == 0:
                    if state.get(i) == 2: continue
                    state[i] = 1
                    stack.append((i, 1))
                    c = nl["cells"][i]
                    for p in self.fn[c["type"]][0]:
                        for b in c["conn"].get(p, []):
                            if isinstance(b, int) and b in self.drv:
                                j = self.drv[b][0]
                                if j in self.seq: continue
                                if state.get(j) == 1: raise SystemExit("comb loop")
                                if state.get(j) != 2: stack.append((j, 0))
                else:
                    if state.get(i) != 2:
                        state[i] = 2; order.append(i)
        self.order = order

    def run(self, src):
        v = dict(src)
        def get(b):
            if b == "0": return 0
            if b == "1": return MASK
            if b in v: return v[b]
            return 0  # undriven / x -> 0 (reported separately)
        for i in self.order:
            c = self.nl["cells"][i]
            ins, outs = self.fn[c["type"]]
            pv = {p: get(c["conn"][p][0]) for p in ins if p in c["conn"]}
            for p, f in outs.items():
                for b in c["conn"].get(p, []):
                    if isinstance(b, int):
                        v[b] = f(pv, MASK)
        return v


def canon(s):
    return s if not (s & 1) else s ^ MASK


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flat", required=True); ap.add_argument("--hier", required=True)
    ap.add_argument("--aliases", required=True); ap.add_argument("--def", dest="deff")
    ap.add_argument("--out", required=True); ap.add_argument("--svg")
    ap.add_argument("--seed", type=int, default=1); ap.add_argument("--fsm")
    a = ap.parse_args()
    lib = liberty()
    A = load_flat(a.flat); B = load_hier_flattened(a.hier)
    # RTL alias sets
    R = json.load(open(a.aliases))
    rm = R["modules"]["tt_um_attention_head_gf"]
    name2canon = {}
    for n, v in rm["netnames"].items():
        if v.get("hide_name"): continue
        for i, b in enumerate(v["bits"]):
            if isinstance(b, int):
                name2canon[bitname(n, i, len(v["bits"]), v)] = b
    def qcanon(nl, c):
        for p in ("Q", "QN"):
            if p in c["conn"]:
                b = c["conn"][p][0]
                for nm in nl["names"].get(b, []):
                    if nm in name2canon:
                        return (name2canon[nm], p)
        return None
    simA, simB = Sim(A, lib), Sim(B, lib)
    rng = random.Random(a.seed)
    src_shared = {}
    def pi_values(nl):
        v = {}
        for pn, (d, bits) in nl["ports"].items():
            if d != "input": continue
            for i, b in enumerate(bits):
                key = ("pi", pn, i)
                if key not in src_shared: src_shared[key] = rng.getrandbits(NV)
                v[b] = src_shared[key]
        return v
    vA, vB = pi_values(A), pi_values(B)
    # ---- flop matching: (1) FSM tables, (2) direct Q-name match, (3) RTL alias set
    fsm = json.load(open(a.fsm)) if a.fsm else {}
    # arithmetic identities ABC used to rename a flop's Q net (documented in fsm_tables.json "_extra_alias")
    xalias = {k: v for k, v in fsm.get("_extra_alias", {}).items() if not k.startswith("_")}
    def qnet(c):
        for p in ("Q", "QN"):
            if p in c["conn"]: return c["conn"][p][0], p
        return None, None
    fsm_flop = {}   # (netlist id, cell index) -> (fsm, states)
    for side, nl, sim in (("flat", A, simA), ("hier", B, simB)):
        for i in sim.seq:
            q, p = qnet(nl["cells"][i])
            for fn_, tab in fsm.items():
                if fn_.startswith("_"): continue
                for nm in nl["names"].get(q, []):
                    if nm in tab[side]:
                        fsm_flop[(side, i)] = (fn_, set(tab[side][nm]))
    st_choice = {fn_: [rng.choice(tab["states"]) for _ in range(NV)] for fn_, tab in fsm.items() if not fn_.startswith("_")}
    def fsm_val(fn_, states):
        v = 0
        for k, s_ in enumerate(st_choice[fn_]):
            if s_ in states: v |= 1 << k
        return v
    bq = {}
    bname = {}
    for i in simB.seq:
        if ("hier", i) in fsm_flop: continue
        q, p = qnet(B["cells"][i])
        for nm in B["names"].get(q, []):
            bname.setdefault(nm, set()).add(i)
            if nm in name2canon: bq.setdefault(name2canon[nm], set()).add(i)
    matched, unmatchedA, how_m = 0, [], Counter()
    usedB = set()
    pair = {}
    for i in simA.seq:
        c = A["cells"][i]; q, p = qnet(c)
        if ("flat", i) in fsm_flop:
            fn_, sts = fsm_flop[("flat", i)]
            v = fsm_val(fn_, sts)
            vA[q] = v if p == "Q" else v ^ MASK
            c["label"] = "core.divider_unit" if fn_ == "divider" else "core"; c["how"] = "flop"
            matched += 1; how_m["fsm"] += 1
            continue
        cands = set()
        for nm in A["names"].get(q, []):
            cands |= bname.get(nm, set())
            if nm in xalias: cands |= bname.get(xalias[nm], set())
        how = "name"
        if len(cands) != 1:
            cands = set()
            for nm in A["names"].get(q, []):
                if nm in name2canon: cands |= bq.get(name2canon[nm], set())
            how = "alias"
        cands -= usedB
        if len(cands) == 1:
            j = cands.pop(); usedB.add(j); pair[i] = j
            key = ("ff", j)
            src_shared[key] = rng.getrandbits(NV)
            vA[q] = src_shared[key] if p == "Q" else src_shared[key] ^ MASK
            qb, pb = qnet(B["cells"][j])
            vB[qb] = src_shared[key] if pb == "Q" else src_shared[key] ^ MASK
            c["label"] = B["cells"][j]["label"]; c["how"] = "flop"
            matched += 1; how_m[how] += 1
        else:
            unmatchedA.append((c["name"], A["names"].get(q, [])))
            vA[q] = rng.getrandbits(NV)
    unmatchedB = []
    for i in simB.seq:
        c = B["cells"][i]; q, p = qnet(c)
        if ("hier", i) in fsm_flop:
            fn_, sts = fsm_flop[("hier", i)]
            v = fsm_val(fn_, sts); vB[q] = v if p == "Q" else v ^ MASK
        elif i not in usedB:
            unmatchedB.append((c["name"], B["names"].get(q, [])))
            vB[q] = rng.getrandbits(NV)
    sA, sB = simA.run(vA), simB.run(vB)
    # hier signature -> labels of the driving cells
    sig2lab = defaultdict(set)
    for i in simB.order:
        c = B["cells"][i]
        for p in simB.fn[c["type"]][1]:
            for b in c["conn"].get(p, []):
                if isinstance(b, int) and b in sB:
                    s = canon(sB[b])
                    if s not in (0,):
                        sig2lab[s].add(c["label"])
    # primary-output check (sanity: both netlists must agree on every PO)
    po_mismatch = 0
    for pn, (d, bits) in A["ports"].items():
        if d != "output": continue
        for i, b in enumerate(bits):
            bb = B["ports"][pn][1][i]
            x = sA.get(b, 0) if isinstance(b, int) else (MASK if b == "1" else 0)
            y = sB.get(bb, 0) if isinstance(bb, int) else (MASK if bb == "1" else 0)
            po_mismatch += x != y
    # flop D check: matched (non-FSM) flops must have equal next-state functions
    d_ok = d_bad = 0; d_bad_list = []
    def dsig(nl, sv, c):
        b = c["conn"].get("D", [None])[0]
        if b == "0": return 0
        if b == "1": return MASK
        return sv.get(b)
    for i, j in pair.items():
        x, y = dsig(A, sA, A["cells"][i]), dsig(B, sB, B["cells"][j])
        if x is not None and x == y: d_ok += 1
        else: d_bad += 1; d_bad_list.append(A["cells"][i]["name"])
    cand = {}
    for i in simA.order:
        c = A["cells"][i]
        labs = set()
        for p in simA.fn[c["type"]][1]:
            for b in c["conn"].get(p, []):
                if isinstance(b, int) and b in sA:
                    labs |= sig2lab.get(canon(sA[b]), set())
        if c["type"].startswith(("tieh", "tiel")):
            continue
        if len(labs) == 1:
            c["label"] = next(iter(labs)); c["how"] = "func-unique"
        elif labs:
            cand[i] = labs; c["how"] = "func-multi"
    # neighbour propagation
    drv = simA.drv
    loads = defaultdict(list)
    for i, c in enumerate(A["cells"]):
        for p in simA.fn[c["type"]][0]:
            for b in c["conn"].get(p, []):
                if isinstance(b, int): loads[b].append(i)
    def nbrs(i):
        c = A["cells"][i]; out = []
        for p in simA.fn[c["type"]][0]:
            for b in c["conn"].get(p, []):
                if isinstance(b, int) and b in drv: out.append(drv[b][0])
        for p in simA.fn[c["type"]][1]:
            for b in c["conn"].get(p, []):
                if isinstance(b, int): out += loads[b]
        return out
    for it in range(50):
        changed = 0
        for i, c in enumerate(A["cells"]):
            if c["label"] is not None and c.get("how") in ("flop", "func-unique"): continue
            cnt = Counter(A["cells"][j]["label"] for j in nbrs(i) if A["cells"][j]["label"])
            if i in cand:
                cnt = Counter({k: v for k, v in cnt.items() if k in cand[i]}) or Counter({k: 1 for k in cand[i]})
            if not cnt: continue
            best = sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            if c["label"] != best:
                c["label"] = best; changed += 1
                if c.get("how") is None: c["how"] = "nbr"
        if not changed: break
    for c in A["cells"]:
        if c["label"] is None: c["label"] = "unlabeled"; c["how"] = "none"
    # summary
    per = defaultdict(lambda: {"cells": 0, "area": 0.0, "seq": 0, "how": Counter(), "by_class": Counter()})
    for c in A["cells"]:
        L = per[c["label"]]; ar = lib[c["type"]]["area"]
        L["cells"] += 1; L["area"] += ar; L["seq"] += cell_class(c["type"]) == "seq"
        L["how"][c["how"]] += 1; L["by_class"][cell_class(c["type"])] += ar
    hier_area = defaultdict(float); hier_cells = Counter()
    for c in B["cells"]:
        hier_area[c["label"]] += lib[c["type"]]["area"]; hier_cells[c["label"]] += 1
    res = {"flat": a.flat, "flat_sha16": sha(a.flat), "hier": a.hier, "hier_sha16": sha(a.hier),
           "vectors": NV, "seed": a.seed, "flops_matched": matched, "flops_unmatched_flat": unmatchedA,
           "flops_unmatched_hier": unmatchedB, "po_mismatches": po_mismatch, "flop_match_how": dict(how_m), "flop_D_function_agree": d_ok, "flop_D_function_differ": d_bad, "flop_D_differ_list": d_bad_list[:40],
           "per_label": {k: {"cells": v["cells"], "area": round(v["area"], 2), "seq": v["seq"],
                             "how": dict(v["how"]), "by_class": {kk: round(vv, 2) for kk, vv in v["by_class"].items()},
                             "hier_area": round(hier_area.get(k, 0), 2), "hier_cells": hier_cells.get(k, 0)}
                         for k, v in sorted(per.items())},
           "cells": {c["name"]: {"type": c["type"], "label": c["label"], "how": c["how"]} for c in A["cells"]}}
    # inter-label nets in the FLAT netlist (physical connectivity between clusters)
    pair_nets = Counter(); pair_pins = Counter()
    port_of = {}
    for pn, (d, bits) in A["ports"].items():
        for b in bits:
            if isinstance(b, int): port_of[b] = "PORT"
    fan = []
    for b, (i, p) in drv.items():
        dl = A["cells"][i]["label"]
        sinks = Counter(A["cells"][j]["label"] for j in loads.get(b, []))
        if b in port_of: sinks["PORT"] += 1
        for sl, k in sinks.items():
            if sl != dl:
                pair_nets[(dl, sl)] += 1; pair_pins[(dl, sl)] += k
        nm = (A["names"].get(b) or [str(b)])[0]
        fan.append({"net": nm, "driver": A["cells"][i]["name"], "driver_label": dl,
                    "fanout": sum(sinks.values()), "sink_labels": dict(sinks)})
    for pn, (d, bits) in A["ports"].items():
        if d != "input": continue
        for k, b in enumerate(bits):
            sinks = Counter(A["cells"][j]["label"] for j in loads.get(b, []))
            for sl, n in sinks.items():
                pair_nets[("PORT", sl)] += 1; pair_pins[("PORT", sl)] += n
            if sinks:
                fan.append({"net": f"{pn}[{k}]", "driver": "PORT", "driver_label": "PORT",
                            "fanout": sum(sinks.values()), "sink_labels": dict(sinks)})
    res["flat_pair_nets"] = [{"from": k[0], "to": k[1], "nets": v, "sink_pins": pair_pins[k]}
                             for k, v in sorted(pair_nets.items(), key=lambda kv: -kv[1])]
    fan.sort(key=lambda f: (-len(f["sink_labels"]), -f["fanout"]))
    res["shared_nets_top"] = [f for f in fan if len(f["sink_labels"]) >= 2][:60]
    res["high_fanout_top"] = sorted(fan, key=lambda f: -f["fanout"])[:40]
    if a.deff:
        D = read_def(a.deff); sizes = lef_sizes()
        res["def"] = a.deff; res["def_sha16"] = sha(a.deff)
        geo = defaultdict(list)
        for c in A["cells"]:
            p = D["comps"].get(c["name"])
            if p is None or p["x"] is None: continue
            w, h = sizes[p["master"]]
            geo[c["label"]].append((p["x"], p["y"], w, h, lib[c["type"]]["area"]))
        out = {}
        for k, v in geo.items():
            xs = [x + w / 2 for x, y, w, h, a_ in v]; ys = [y + h / 2 for x, y, w, h, a_ in v]
            n = len(v); cx = sum(xs) / n; cy = sum(ys) / n
            sx = (sum((x - cx) ** 2 for x in xs) / n) ** 0.5; sy = (sum((y - cy) ** 2 for y in ys) / n) ** 0.5
            bb = [min(x for x, *_ in v), min(y for _, y, *_ in v), max(x + w for x, y, w, *_ in v), max(y + h for x, y, w, h, _ in v)]
            bba = (bb[2] - bb[0]) * (bb[3] - bb[1])
            out[k] = {"n": n, "centroid": [round(cx, 2), round(cy, 2)], "rms_spread": [round(sx, 2), round(sy, 2)],
                      "bbox": [round(t, 2) for t in bb], "bbox_area": round(bba, 1),
                      "cell_area_over_bbox": round(sum(a_ for *_, a_ in v) / bba, 4) if bba else None}
        res["placement"] = out
        # neighbourhood purity: share of each cell's 6 nearest placed cells with the same label
        pts = [(c["label"], D["comps"][c["name"]]["x"], D["comps"][c["name"]]["y"]) for c in A["cells"]
               if c["name"] in D["comps"] and D["comps"][c["name"]]["x"] is not None]
        grid = defaultdict(list)
        for k, x, y in pts: grid[(int(x // 10), int(y // 10))].append((k, x, y))
        pur = defaultdict(list)
        for k, x, y in pts:
            gx, gy = int(x // 10), int(y // 10)
            near = [q for dx in (-1, 0, 1) for dy in (-1, 0, 1) for q in grid[(gx + dx, gy + dy)] if q[1:] != (x, y)]
            near.sort(key=lambda q: abs(q[1] - x) + abs(q[2] - y))
            near = near[:6]
            if near: pur[k].append(sum(q[0] == k for q in near) / len(near))
        for k in out:
            out[k]["nn6_same_label"] = round(sum(pur[k]) / len(pur[k]), 3) if pur[k] else None
        if a.svg:
            write_svg(a.svg, D, A, sizes, lib)
    json.dump(res, open(a.out, "w"), indent=1)
    print(f"flops matched {matched} {dict(how_m)}, unmatched flat {len(unmatchedA)} hier {len(unmatchedB)}, PO mismatches {po_mismatch}, D-agree {d_ok} differ {d_bad}")
    for k, v in res["per_label"].items():
        print(f"  {k:24s} cells {v['cells']:5d} area {v['area']:9.1f} ff {v['seq']:3d}  hier {v['hier_area']:9.1f} ({v['hier_cells']:4d})  how {v['how']}")
    if "placement" in res:
        for k, v in res["placement"].items():
            print(f"  {k:24s} centroid {v['centroid']} rms {v['rms_spread']} bbox {v['bbox']} fill {v['cell_area_over_bbox']} nn6 {v['nn6_same_label']}")


COLORS = {"top": "#d62728", "core": "#7f7f7f", "core.mac": "#1f77b4", "core.mac.adder": "#17becf",
          "core.mac.l_adder": "#9edae5", "core.max_unit": "#ff7f0e", "core.exponent_unit": "#2ca02c",
          "core.divider_unit": "#9467bd", "unlabeled": "#000000"}


def write_svg(path, D, A, sizes, lib):
    die = D["die"]; W, H = die[2] - die[0], die[3] - die[1]
    s = 3.0
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W*s:.1f} {H*s+70:.1f}" width="{W*s:.0f}" height="{H*s+70:.0f}">',
           f'<rect x="0" y="0" width="{W*s:.1f}" height="{H*s:.1f}" fill="#f4f5f7" stroke="#999"/>']
    for r in D["rows"]:
        out.append(f'<rect x="{r["x"]*s:.1f}" y="{(H-r["y"]-3.92)*s:.1f}" width="{r["n"]*r["step"]*s:.1f}" height="{3.92*s:.1f}" fill="none" stroke="#e0e3e8" stroke-width="0.4"/>')
    lab = {c["name"]: c["label"] for c in A["cells"]}
    for n, p in D["comps"].items():
        if p["x"] is None: continue
        m = p["master"]
        if m.startswith(("fill", "decap")) or m not in sizes: continue
        w, h = sizes[m]
        if m.startswith(("filltie", "endcap")): col = "#c9ced6"
        elif n in lab: col = COLORS.get(lab[n], "#000")
        else: col = "#444444"  # CTS / repair / tie inserted by PnR
        out.append(f'<rect x="{p["x"]*s:.2f}" y="{(H-p["y"]-h)*s:.2f}" width="{w*s:.2f}" height="{h*s:.2f}" fill="{col}"/>')
    for pn, p in D["pins"].items():
        out.append(f'<rect x="{p["x"]*s-1:.1f}" y="{(H-p["y"])*s-2:.1f}" width="2" height="4" fill="#000"/>')
    x = 6
    for k, c in list(COLORS.items())[:-1] + [("PnR-inserted (CTS/repair/tie)", "#444444")]:
        out.append(f'<rect x="{x}" y="{H*s+12}" width="10" height="10" fill="{c}"/><text x="{x+14}" y="{H*s+21}" font-size="11" font-family="sans-serif">{k}</text>')
        x += 14 + 7 * len(k) + 12
    out.append(f'<text x="6" y="{H*s+50}" font-size="11" font-family="sans-serif">h2 final DEF, cells coloured by RTL module (attribute.py). Die {W:.2f} x {H:.2f} um. Pins on the top edge.</text>')
    out.append("</svg>")
    open(path, "w").write("\n".join(out))


if __name__ == "__main__":
    main()
