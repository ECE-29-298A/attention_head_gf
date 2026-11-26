#!/usr/bin/env python3
"""attrib.py <synth_netlist.v> <final_def> <final_netlist.v> <out.json>

In-context attribution of a FLAT shipped-flow netlist to RTL modules, and where those cells
landed in a placed/routed DEF.

Flops are mapped by Q net (stable names, PLAN.md section 3). Combinational cells are mapped by
cone: DEST(c) = flop groups reachable from c's output through combinational logic (plus PO),
SRC(c) = flop groups / primary inputs in c's fan-in.
  module(c) = the single module in DEST(c), else "shared:<A+B>".
  exp_lut refinement: a MAC-destined cell whose SRC is only {S register, score_shift} computes
  a function of (D, shift) alone, i.e. exp_lut's table (W feeds only the accumulate path).
  Output-only logic (DEST = {PO}) is attributed to FE (the TT pin interface).
Placement metrics (final DEF): bbox, centroid, RMS spread, bin purity (10 x 10 um bins),
bbox overlap per pair. Wire: routed length of every signal net, classified internal/inter by the
modules of its connected cells (repair buffers inherit their driver's module; clock nets apart).
"""
import json, os, re, sys, math
from collections import Counter, defaultdict
sys.path.insert(0, os.path.dirname(__file__))
import pdlib

FLOP_GROUPS = [  # (regex on Q net, group, module)
    (r"^config_chain\[[0-3]\]$", "FE_last", "FE"),
    (r"^config_chain\[[4-7]\]$", "FE_shift", "FE"),
    (r"^config_chain\[8\]$", "FE_cont", "FE"),
    (r"^(sck_sync|cs_sync)\[", "FE_sync", "FE"),
    (r"^core\.exponent_unit\.D\[", "MAC_S", "MAC"),
    (r"^core\.mac\.ring\[|^core\.divider_unit\.sum_in\[|^core\.divider_unit\.magnitude\[0\]$", "MAC_RING", "MAC"),
    (r"^core\.divider_unit\.denominator\[", "MAC_L", "MAC"),
    (r"^core\.mac\.M\[", "MAX_M", "MAX"),
    (r"^core\.divider_unit\.|^core\.div_done$", "DIV", "DIV"),
    (r"^core\.", "CTRL", "CTRL"),
]
MODULES = ["FE", "CTRL", "MAC", "EXP", "MAX", "DIV"]
OUTPINS = None


def flop_group(q):
    for rx, g, m in FLOP_GROUPS:
        if re.search(rx, q):
            return g, m
    raise ValueError(q)


def main(syn_nl, fdef, fnl, out):
    A = pdlib.liberty_areas()
    L = pdlib.lef_macros()
    mods = pdlib.parse_netlist(syn_nl)
    top = pdlib.top_module(mods)
    cells = pdlib.flatten_cells(mods, top)
    ports = {}
    for kind, name, msb, lsb in mods[top].ports:
        for b in mods[top].bits(name):
            ports[b] = kind
    info = {}
    drv, loads = {}, defaultdict(list)
    for path, m, pins, _ in cells:
        info[path] = {"master": m, "pins": pins}
        for p, net in pins.items():
            if net is None or net.startswith("1'b"):
                continue
            if L[m]["dir"].get(p) == "OUTPUT":
                drv[net] = path
            else:
                loads[net].append((path, p))
    isflop = lambda c: info[c]["master"].replace(pdlib.PFX, "").startswith(("dff", "sdff"))
    istie = lambda c: info[c]["master"].replace(pdlib.PFX, "").startswith(("tieh", "tiel"))
    group, module = {}, {}
    for c in info:
        if isflop(c):
            g, mm = flop_group(info[c]["pins"]["Q"])
            group[c], module[c] = g, mm
    outs = lambda c: [n for p, n in info[c]["pins"].items()
                      if n and not n.startswith("1'b") and L[info[c]["master"]]["dir"].get(p) == "OUTPUT"]
    ins = lambda c: [n for p, n in info[c]["pins"].items()
                     if n and not n.startswith("1'b") and L[info[c]["master"]]["dir"].get(p) == "INPUT"]
    # DEST (memoized DFS over the combinational fan-out)
    dest = {}

    def D(c):
        if c in dest:
            return dest[c]
        dest[c] = set()  # cycle guard (no comb loops expected)
        s = set()
        for n in outs(c):
            if ports.get(n) == "output":
                s.add("PO")
            for l, p in loads[n]:
                if isflop(l):
                    s.add(group[l])
                else:
                    s |= D(l)
        dest[c] = s
        return s
    src = {}

    def S(c):
        if c in src:
            return src[c]
        src[c] = set()
        s = set()
        for n in ins(c):
            if ports.get(n) == "input":
                s.add("PI:" + re.sub(r"\[\d+\]", "", n))
            d = drv.get(n)
            if d is None:
                continue
            if isflop(d):
                s.add(group[d])
            else:
                s |= S(d)
        src[c] = s
        return s
    gmod = {g: m for _, g, m in FLOP_GROUPS}
    gmod["PO"] = "PO"
    for c in info:
        if isflop(c):
            continue
        ds = D(c)
        ms = {gmod[g] for g in ds}
        if istie(c):
            # ties: attributed by their loads' modules
            lm = set()
            for n in outs(c):
                for l, p in loads[n]:
                    lm.add(module.get(l) or "?")
            module[c] = "tie"
            continue
        if ms == {"MAC"} and S(c) <= {"MAC_S", "FE_shift"}:
            module[c] = "EXP"
        elif len(ms) == 1:
            m = next(iter(ms))
            module[c] = "FE" if m == "PO" else m
        elif not ms:
            module[c] = "dead"
        else:
            ms.discard("PO")
            module[c] = next(iter(ms)) if len(ms) == 1 else "shared:" + "+".join(sorted(ms))
    # second pass: resolve tie cells to the module of their loads (majority)
    for c in info:
        if module.get(c) == "tie":
            lm = Counter()
            for n in outs(c):
                for l, p in loads[n]:
                    lm[module.get(l, "?")] += 1
            module[c] = "tie:" + (lm.most_common(1)[0][0] if lm else "none")
    # --- per-module synthesis stats
    stats = defaultdict(lambda: {"cells": 0, "area": 0.0, "flops": 0, "flop_area": 0.0, "masters": Counter()})
    for c, m in module.items():
        s = stats[m]
        a = A[info[c]["master"]]
        s["cells"] += 1
        s["area"] += a
        if isflop(c):
            s["flops"] += 1
            s["flop_area"] += a
        s["masters"][info[c]["master"].replace(pdlib.PFX, "")] += 1
    # --- cut nets between modules (synthesized connectivity)
    def base(m):
        return m.split(":")[0] if m.startswith("tie") else m
    cut = Counter()
    cut_nets = defaultdict(list)
    for n, d in drv.items():
        md = module[d]
        lm = {module[l] for l, p in loads[n]}
        for x in lm:
            if x != md:
                cut[(md, x)] += 1
                if len(cut_nets[(md, x)]) < 400:
                    cut_nets[(md, x)].append(n)
        if ports.get(n) == "output":
            cut[(md, "PO")] += 1
    for n, kind in ports.items():
        if kind == "input":
            for x in {module[l] for l, p in loads.get(n, [])}:
                cut[("PI", x)] += 1
    # --- fanout of shared / broadcast signals
    fan = []
    for n, d in drv.items():
        ls = loads[n]
        if len(ls) < 8:
            continue
        lm = Counter(module[l] for l, p in ls)
        fan.append({"net": n, "fanout": len(ls), "driver": d, "driver_master": info[d]["master"].replace(pdlib.PFX, ""),
                    "driver_module": module[d], "load_modules": dict(lm.most_common())})
    for n, kind in ports.items():
        if kind == "input" and len(loads.get(n, [])) >= 1:
            lm = Counter(module[l] for l, p in loads[n])
            fan.append({"net": n, "fanout": len(loads[n]), "driver": "PI", "driver_master": "-", "driver_module": "PI",
                        "load_modules": dict(lm.most_common())})
    fan.sort(key=lambda x: -x["fanout"])
    # reset net: the cell combining rst_n and ena
    rst = [c for c in info if set(ins(c)) >= {"rst_n", "ena"}]
    # --- placement in the final DEF
    Dd = pdlib.parse_def(fdef)
    fmods = pdlib.parse_netlist(fnl)
    fcells = pdlib.flatten_cells(fmods)
    fdrv = {}
    for path, m, pins, _ in fcells:
        for p, net in pins.items():
            if net and L[m]["dir"].get(p) == "OUTPUT":
                fdrv[net] = path
    finfo = {p: (m, pins) for p, m, pins, _ in fcells}
    REP = re.compile(r"^(fanout|load_slew|wire|rebuffer|split|max_cap|max_length|hold|input|output)\d+")
    CLK = re.compile(r"^(clkbuf_|clkload|delaybuf)")
    fmod = {}
    for c in finfo:
        if c in module:
            fmod[c] = module[c]
        elif CLK.match(c):
            fmod[c] = "CLKTREE"
        elif c.startswith("tt_um_attention_head_gf_") or finfo[c][0].replace(pdlib.PFX, "").startswith(("tieh", "tiel")):
            fmod[c] = "tie:new"
    # repair buffers inherit the module of the synthesized driver upstream of their input
    def upstream(c, depth=0):
        m, pins = finfo[c]
        for p, net in pins.items():
            if L[m]["dir"].get(p) == "INPUT" and net:
                d = fdrv.get(net)
                if d is None:
                    return "PI"
                if d in module:
                    return module[d]
                if depth < 10:
                    return upstream(d, depth + 1)
        return "?"
    for c in finfo:
        if REP.match(c):
            fmod[c] = "repair:" + upstream(c)
    for c in finfo:
        fmod.setdefault(c, "other")
    comp = Dd["comps"]
    pl = defaultdict(list)
    for c, m in fmod.items():
        if c not in comp or comp[c]["x"] is None:
            continue
        w, h = L[comp[c]["master"]]["w"], L[comp[c]["master"]]["h"]
        pl[m].append((comp[c]["x"], comp[c]["y"], w, h))
    BIN = 10.0
    bins = defaultdict(Counter)
    for m, lst in pl.items():
        for x, y, w, h in lst:
            bins[(int((x + w / 2) // BIN), int((y + h / 2) // BIN))][m] += w * h
    place = {}
    for m, lst in pl.items():
        if not lst:
            continue
        ar = sum(w * h for _, _, w, h in lst)
        cx = sum((x + w / 2) * w * h for x, y, w, h in lst) / ar
        cy = sum((y + h / 2) * w * h for x, y, w, h in lst) / ar
        rms = math.sqrt(sum(((x + w / 2 - cx) ** 2 + (y + h / 2 - cy) ** 2) * w * h for x, y, w, h in lst) / ar)
        bb = (min(x for x, _, _, _ in lst), min(y for _, y, _, _ in lst),
              max(x + w for x, _, w, _ in lst), max(y + h for _, y, _, h in lst))
        own = 0.0
        for x, y, w, h in lst:
            b = bins[(int((x + w / 2) // BIN), int((y + h / 2) // BIN))]
            own += w * h * b[m] / sum(b.values())
        place[m] = {"cells": len(lst), "area": round(ar, 2), "centroid": [round(cx, 2), round(cy, 2)],
                    "rms_spread_um": round(rms, 2), "bbox": [round(v, 2) for v in bb],
                    "bbox_area": round((bb[2] - bb[0]) * (bb[3] - bb[1]), 1),
                    "bbox_fill": round(ar / ((bb[2] - bb[0]) * (bb[3] - bb[1])), 3),
                    "bin_purity": round(own / ar, 3)}
    main_mods = [m for m in MODULES if m in place]
    overlap = {}
    for a in main_mods:
        for b in main_mods:
            if a == b:
                continue
            A1, B1 = place[a]["bbox"], place[b]["bbox"]
            ix = max(0, min(A1[2], B1[2]) - max(A1[0], B1[0]))
            iy = max(0, min(A1[3], B1[3]) - max(A1[1], B1[1]))
            overlap[f"{a}|{b}"] = round(ix * iy / place[a]["bbox_area"], 3)
    # wire per module (routed nets)
    wire = Counter()
    wire_pair = Counter()
    nets_cls = Counter()
    for n, d in Dd["nets"].items():
        ms = set()
        for c, p in d["conns"]:
            if c == "PIN":
                ms.add("PIN")
                continue
            m = fmod.get(c, "other")
            if m.startswith("repair:"):
                m = m.split(":", 1)[1]
            if m.startswith("tie"):
                continue
            ms.add(m)
        if "CLKTREE" in ms or n in ("clk",) or re.match(r"^clknet", n):
            wire["CLOCK"] += d["len"]
            nets_cls["CLOCK"] += 1
            continue
        ms.discard("tie")
        if len(ms) == 1:
            m = next(iter(ms))
            wire[m] += d["len"]
            nets_cls[m] += 1
        else:
            key = "+".join(sorted(ms))
            wire_pair[key] += d["len"]
            nets_cls["inter"] += 1
    res = {
        "inputs": {"synth_netlist": syn_nl, "synth_sha": pdlib.sha(syn_nl), "final_def": fdef,
                   "final_def_sha": pdlib.sha(fdef), "final_netlist": fnl, "final_netlist_sha": pdlib.sha(fnl)},
        "flop_groups": dict(Counter(group.values())),
        "modules": {m: {"cells": s["cells"], "area": round(s["area"], 2), "flops": s["flops"],
                        "flop_area": round(s["flop_area"], 2), "top_masters": dict(s["masters"].most_common(12))}
                    for m, s in sorted(stats.items())},
        "total_area": round(sum(s["area"] for s in stats.values()), 3),
        "cut_bits": {f"{a}->{b}": c for (a, b), c in sorted(cut.items(), key=lambda x: -x[1])},
        "cut_net_examples": {f"{a}->{b}": v[:12] for (a, b), v in cut_nets.items()},
        "fanout_top": fan[:40],
        "reset_cells": [(c, info[c]["master"].replace(pdlib.PFX, ""), [len(loads[n]) for n in outs(c)]) for c in rst],
        "placement": place, "bbox_overlap_frac": overlap,
        "wire_internal_um": {k: round(v, 1) for k, v in wire.most_common()},
        "wire_inter_um": {k: round(v, 1) for k, v in wire_pair.most_common()},
        "net_counts": dict(nets_cls),
        "routed_total_um": round(sum(d["len"] for d in Dd["nets"].values()), 1),
        "module_of_cell": module,
    }
    json.dump(res, open(out, "w"), indent=1)
    print("total synth area", res["total_area"])
    for m, s in res["modules"].items():
        print(f"{m:22s} cells {s['cells']:5d} area {s['area']:10.2f} flops {s['flops']:4d}")
    print("cut:", list(res["cut_bits"].items())[:30])
    for m, p in place.items():
        print(m, p)
    print("overlap", overlap)
    print("wire internal", res["wire_internal_um"])
    print("wire inter", list(res["wire_inter_um"].items())[:20])
    print("routed total", res["routed_total_um"])


if __name__ == "__main__":
    main(*sys.argv[1:5])
