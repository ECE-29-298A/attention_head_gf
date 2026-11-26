#!/usr/bin/env python3
"""Structural checks of a hardened ripple_add block (PLAN.md section 7, item 2).

Usage: check_block.py N RUN_DIR OUT.json

RUN_DIR is impl/n<N>/run (copied back by run_block.sh). Checks:
  P1 every planned instance (block_n<N>.cfg) is FIXED at the exact location/orientation, same master,
     in the ManualMacroPlacement DEF and every later step DEF and the final DEF;
  P2 no instance overlaps another; every non-planned instance is a physical cell
     (endcap/fill/fillcap) and there is no WELLTAP inside the core; endcaps at both ends of every row;
  P3 pins: side and bit row as in block_n<N>_pins.cfg / PLAN 5.5 (bit i's pins inside row i);
  P4 netlist: final nl and pnl logic instances equal the approved netlist (master + every pin's net,
     after resolving the c[0] = cin alias);
  P5 routing: signal wires only on Metal2-Metal4 (Metal1 appears only as via-access points);
     every signal net routed;
  P6 die/core size and bounding box.
Exit 0 only if all checks pass.
"""
import gzip
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLAN_OUT = HERE.parents[1] / "layout_plan" / "out"
LEF = Path("/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/"
           "54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/"
           "gf180mcu_fd_sc_mcu7t5v0/lef/gf180mcu_fd_sc_mcu7t5v0.lef")
DBU = 2000
PHYS = re.compile(r"__(endcap|fill_\d+|fillcap_\d+|filltie)$")


def lef_sizes():
    sizes, cls, cur = {}, {}, None
    for line in LEF.read_text().splitlines():
        t = line.split()
        if not t:
            continue
        if t[0] == "MACRO":
            cur = t[1]
        elif t[0] == "CLASS" and cur and cur not in cls:
            cls[cur] = " ".join(t[1:]).rstrip(" ;")
        elif t[0] == "SIZE" and cur:
            sizes[cur] = (float(t[1]), float(t[3]))
    return sizes, cls


def read(p):
    p = Path(p)
    return gzip.open(p, "rt").read() if p.suffix == ".gz" else p.read_text()


def components(text):
    sec = re.search(r"^COMPONENTS \d+ ;(.*?)^END COMPONENTS", text, re.S | re.M).group(1)
    out = {}
    for m in re.finditer(r"- (\S+) (\S+)(.*?);", sec, re.S):
        name, master, rest = m.group(1).replace("\\", ""), m.group(2), m.group(3)
        pm = re.search(r"\+ (FIXED|PLACED|FIRM|COVER) \( (-?\d+) (-?\d+) \) (\w+)", rest)
        out[name] = (master, pm.group(1), int(pm.group(2)), int(pm.group(3)), pm.group(4)) if pm \
            else (master, "UNPLACED", None, None, None)
    return out


def pins(text):
    sec = re.search(r"^PINS \d+ ;(.*?)^END PINS", text, re.S | re.M).group(1)
    out = {}
    for m in re.finditer(r"- (\S+) \+ NET.*?LAYER (\w+) \( (-?\d+) (-?\d+) \) \( (-?\d+) (-?\d+) \)"
                         r".*?\+ (?:PLACED|FIXED) \( (-?\d+) (-?\d+) \)", sec, re.S):
        name, layer = m.group(1), m.group(2)
        x1, y1, x2, y2, cx, cy = map(int, m.groups()[2:])
        out[name] = (layer, (cx + x1) / DBU, (cy + y1) / DBU, (cx + x2) / DBU, (cy + y2) / DBU)
    return out


def parse_verilog_instances(text):
    """{instance: (master, {pin: net})} for cell instances with named connections."""
    text = re.sub(r"//.*", "", text)
    alias = dict((a.replace("\\", "").strip(), b.replace("\\", "").strip())
                 for a, b in re.findall(r"assign\s+(\S+)\s*=\s*([^;]+);", text))
    inst = {}
    for m in re.finditer(r"(gf180mcu_\w+)\s+(\\?\S+)\s*\((.*?)\);", text, re.S):
        master, name, conns = m.group(1), m.group(2).replace("\\", "").strip(), m.group(3)
        pins_ = {}
        for p, n in re.findall(r"\.(\w+)\s*\(\s*([^()]*?)\s*\)", conns):
            n = n.replace("\\", "").replace(" ", "")
            pins_[p] = alias.get(n, n)
        inst[name] = (master, pins_)
    return inst, alias


def approved_instances(n):
    """The approved netlist uses a generate loop; expand it (and check the text matches)."""
    src = (PLAN_OUT / f"ripple_add_n{n}.v").read_text()
    assert "assign c[0] = cin;" in src
    assert re.search(r"addf_1 u_fa \(\.A\(a\[i\]\), \.B\(b\[i\]\), \.CI\(c\[i\]\), "
                     r"\.S\(s\[i\]\), \.CO\(c\[i \+ 1\]\)\);", src)
    m = re.search(r"xor3_1 u_msb_x3 \(\.A1\(b\[(\d+)\]\), \.A2\(a\[(\d+)\]\), \.A3\(c\[(\d+)\]\), "
                  r"\.Z\(s\[(\d+)\]\)\);", src)
    assert m and all(int(g) == n - 1 for g in m.groups())
    c = lambda i: "cin" if i == 0 else f"c[{i}]"
    inst = {f"bitslice[{i}].u_fa": ("gf180mcu_fd_sc_mcu7t5v0__addf_1",
                                    {"A": f"a[{i}]", "B": f"b[{i}]", "CI": c(i), "S": f"s[{i}]",
                                     "CO": f"c[{i + 1}]"}) for i in range(n - 1)}
    inst["u_msb_x3"] = ("gf180mcu_fd_sc_mcu7t5v0__xor3_1",
                        {"A1": f"b[{n-1}]", "A2": f"a[{n-1}]", "A3": c(n - 1), "Z": f"s[{n-1}]"})
    return inst


def main():
    n, run, outp = int(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    sizes, cls = lef_sizes()
    res, ok = {"N": n, "checks": {}}, True

    def put(k, passed, **d):
        nonlocal ok
        ok &= bool(passed)
        res["checks"][k] = {"pass": bool(passed), **d}

    plan = {}
    for line in (PLAN_OUT / f"block_n{n}.cfg").read_text().splitlines():
        nm, x, y, o = line.split()
        plan[nm] = (round(float(x) * DBU), round(float(y) * DBU), o)
    masters = {k: v[0] for k, v in approved_instances(n).items()}
    final = read(run / "final/def/ripple_add.def")
    steps = sorted((run / "steps").glob("*/*.def.gz"), key=lambda p: int(p.parent.name.split("-")[0]))
    first = next(i for i, p in enumerate(steps) if "manualmacroplacement" in p.parent.name)
    checked, bad = [], []
    for p in steps[first:] + [run / "final/def/ripple_add.def"]:
        comps = components(read(p))
        for nm, (x, y, o) in plan.items():
            c = comps.get(nm)
            if not c or c[0] != masters[nm] or c[1] != "FIXED" or (c[2], c[3], c[4]) != (x, y, o):
                bad.append((str(p.parent.name if p.suffix == ".gz" else "final"), nm, c))
        checked.append(p.parent.name if p.suffix == ".gz" else "final")
    put("P1_fixed_exact", not bad, defs_checked=len(checked), first=checked[0], bad=bad[:10])

    comps = components(final)
    rows = [(int(a), int(b), o, int(c)) for a, b, o, c in
            re.findall(r"^ROW \S+ \S+ (\d+) (\d+) (\w+) DO (\d+) BY 1", final, re.M)]
    rects, extra, welltap = [], {}, 0
    for nm, (mst, st, x, y, o) in comps.items():
        w, h = sizes[mst]
        rects.append((nm, x, y, x + round(w * DBU), y + round(h * DBU)))
        if nm not in plan:
            extra[mst.split("__")[1]] = extra.get(mst.split("__")[1], 0) + 1
            if not PHYS.search(mst):
                put("P2_extra_is_physical", False, offender=nm)
            if "WELLTAP" in cls.get(mst, ""):
                welltap += 1
    ov = []
    rects.sort(key=lambda r: r[1])
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            if b[1] >= a[3]:
                break
            if a[2] < b[4] and b[2] < a[4]:
                ov.append((a[0], b[0]))
    ends_ok = True
    for x0, y0, o, cnt in rows:
        x1 = x0 + cnt * 1120
        here = [(nm, r) for nm, *r in rects if r[1] == y0]
        left = any(comps[nm][0].endswith("__endcap") and r[0] == x0 for nm, r in here)
        right = any(comps[nm][0].endswith("__endcap") and r[2] == x1 for nm, r in here)
        ends_ok &= left and right
    used = sum((r[3] - r[1]) for r in rects)
    put("P2_cells", not ov and welltap == 0 and ends_ok, overlaps=ov[:5], welltaps=welltap,
        endcaps_both_ends_all_rows=ends_ok, rows=len(rows), extra_cells=extra,
        row_fill_fraction=round(used / sum(c * 1120 for *_, c in rows), 4))

    pp = pins(final)
    die = [int(v) / DBU for v in re.search(r"DIEAREA \( (\d+) (\d+) \) \( (\d+) (\d+) \)", final).groups()]
    core_y0 = rows[0][1] / DBU
    perr = []
    for nm, (layer, x1, y1, x2, y2) in pp.items():
        if nm in ("VPWR", "VGND"):
            continue
        m = re.match(r"([abs])\[(\d+)\]$", nm)
        if nm == "cin":
            side_ok = y1 == die[1] and layer == "Metal2"
            row_ok = True
        else:
            k, i = m.group(1), int(m.group(2))
            side_ok = (x1 == die[0] if k in "as" else x2 == die[2]) and layer == "Metal3"
            lo, hi = core_y0 + 3.92 * i, core_y0 + 3.92 * (i + 1)
            row_ok = lo <= y1 and y2 <= hi
        if not (side_ok and row_ok):
            perr.append((nm, layer, x1, y1, x2, y2))
    put("P3_pins", not perr and len(pp) == 3 * n + 1 + 2, pins=len(pp), errors=perr[:10],
        power_pins={k: pp[k] for k in ("VPWR", "VGND") if k in pp})

    appr = approved_instances(n)
    for tag, f in (("nl", "final/nl/ripple_add.nl.v"), ("pnl", "final/pnl/ripple_add.pnl.v")):
        inst, alias = parse_verilog_instances((run / f).read_text())
        logic = {k: (m, {p: v for p, v in c.items() if p not in ("VDD", "VSS", "VNW", "VPW")})
                 for k, (m, c) in inst.items() if not PHYS.search(m)}
        diffs = [k for k in set(logic) | set(appr) if logic.get(k) != appr.get(k)]
        put(f"P4_netlist_{tag}", not diffs, logic_instances=len(logic), diffs=diffs[:10],
            assigns=alias)

    nets = re.search(r"^NETS \d+ ;(.*?)^END NETS", final, re.S | re.M).group(1)
    wire_layers, unrouted, m1_wires = {}, [], 0
    for m in re.finditer(r"- (\S+)(.*?);", nets, re.S):
        body = m.group(2)
        if "+ ROUTED" not in body:
            unrouted.append(m.group(1))
        for lay, seg in re.findall(r"(Metal\d) (\( [^;]*?)(?=\n|NEW|$)", body):
            pts = re.findall(r"\(", seg)
            is_wire = len(pts) >= 2
            if is_wire:
                wire_layers[lay] = wire_layers.get(lay, 0) + 1
                if lay in ("Metal1", "Metal5"):
                    m1_wires += 1
    put("P5_routing", not unrouted and m1_wires == 0 and set(wire_layers) <= {"Metal2", "Metal3", "Metal4"},
        unrouted=unrouted, wire_segments_by_layer=wire_layers)

    xs = [r[1] for r in rects if r[0] in plan] + [r[3] for r in rects if r[0] in plan]
    ys = [r[2] for r in rects if r[0] in plan] + [r[4] for r in rects if r[0] in plan]
    bw, bh = (max(xs) - min(xs)) / DBU, (max(ys) - min(ys)) / DBU
    corea = (rows[0][0] / DBU, rows[0][1] / DBU,
             (rows[0][0] + rows[0][3] * 1120) / DBU, (rows[-1][1] + 7840) / DBU)
    cell_area = sum(sizes[masters[k]][0] * sizes[masters[k]][1] for k in plan)
    put("P6_size", True, die_um=die, die_area_um2=round((die[2] - die[0]) * (die[3] - die[1]), 2),
        core_um=corea, core_area_um2=round((corea[2] - corea[0]) * (corea[3] - corea[1]), 2),
        bbox_um=[min(xs) / DBU, min(ys) / DBU, max(xs) / DBU, max(ys) / DBU],
        bbox_wh_um=[bw, bh], bbox_area_um2=round(bw * bh, 2),
        logic_cell_area_um2=round(cell_area, 2), bbox_utilization=round(cell_area / (bw * bh), 4))
    res["all_pass"] = ok
    outp.write_text(json.dumps(res, indent=1) + "\n")
    for k, v in res["checks"].items():
        print(k, "PASS" if v["pass"] else "FAIL")
    print("ALL_PASS" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
