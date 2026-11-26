#!/usr/bin/env python3
"""Cell census of a LibreLane netlist: count and area by master and by origin group.

usage: census.py <netlist.nl.v> [--json out.json] [--ref other.nl.v]

Origin groups come from instance-name prefixes the OpenROAD tools give inserted cells:
  CTS        clkbuf_* / clkload* / clknet / delaybuf (TritonCTS), and any clkbuf/clkinv master
  repair     fanout*/max_cap*/max_length*/split*/wire*/rebuffer*/load_slew*/input*/output*/hold*
  tap/endcap TAP_*/PHY_EDGE_ROW_* (and filltie/endcap masters)
  tie        tieh/tiel masters
  logic      everything else (synthesis cells, possibly resized)
Areas come from the LEF SIZE of each master.
"""
import json
import re
import sys
from collections import Counter, defaultdict

LEF = ("/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/"
       "54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/"
       "gf180mcu_fd_sc_mcu7t5v0/lef/gf180mcu_fd_sc_mcu7t5v0.lef")
PFX = "gf180mcu_fd_sc_mcu7t5v0__"


def lef_areas():
    areas, cur = {}, None
    for line in open(LEF):
        m = re.match(r"\s*MACRO\s+(\S+)", line)
        if m:
            cur = m.group(1)
            continue
        m = re.match(r"\s*SIZE\s+([\d.]+)\s+BY\s+([\d.]+)", line)
        if m and cur:
            areas[cur] = float(m.group(1)) * float(m.group(2))
    return areas


INST_RE = re.compile(r"^\s*(" + PFX + r"\S+)\s+(\\?\S+)\s*\(", re.M)


def instances(path):
    txt = open(path).read()
    return [(m.group(1), m.group(2)) for m in INST_RE.finditer(txt)]


def group(master, inst):
    short = master[len(PFX):]
    if short.startswith(("filltie", "endcap", "fill_", "fillcap")):
        return "tap_endcap"
    if short.startswith(("tieh", "tiel")):
        return "tie"
    # instance name first: the resizer also uses clkbuf_* masters for repair buffers, and
    # synthesis uses clkinv_1 as a logic inverter
    if re.match(r"\\?(clkbuf_|clkload|clknet|delaybuf)", inst):
        return "cts"
    if re.match(r"\\?(fanout|max_cap|max_length|split|wire|rebuffer|load_slew|input|output|hold|place|"
                r"ANTENNA|rsz)", inst):
        return "repair"
    return "logic"


def census(path):
    areas = lef_areas()
    by_master = Counter()
    by_group = defaultdict(float)
    by_group_master = defaultdict(Counter)
    insts = instances(path)
    for master, inst in insts:
        g = group(master, inst)
        if g == "tap_endcap" and master[len(PFX):].startswith(("fill_", "fillcap")):
            continue  # fillers are not std-cell area
        by_master[master[len(PFX):]] += 1
        by_group[g] += areas[master]
        by_group_master[g][master[len(PFX):]] += 1
    total = sum(by_group.values())
    return {
        "netlist": path,
        "total_um2": round(total, 3),
        "count": sum(by_master.values()),
        "by_group_um2": {k: round(v, 3) for k, v in sorted(by_group.items())},
        "by_group_master": {g: dict(sorted(c.items())) for g, c in by_group_master.items()},
        "by_master": dict(sorted(by_master.items())),
    }


def main():
    args = sys.argv[1:]
    out = None
    ref = None
    if "--json" in args:
        i = args.index("--json"); out = args[i + 1]; del args[i:i + 2]
    if "--ref" in args:
        i = args.index("--ref"); ref = args[i + 1]; del args[i:i + 2]
    c = census(args[0])
    areas = lef_areas()
    print(f"{c['netlist']}\n total {c['total_um2']:.1f} um2, {c['count']} cells")
    for g, a in c["by_group_um2"].items():
        print(f"  {g:11s} {a:10.1f}  {dict(c['by_group_master'][g]) if g in ('cts', 'repair', 'tie') else ''}")
    if ref:
        r = census(ref)
        print(f" delta vs {ref}: {c['total_um2'] - r['total_um2']:+.1f} um2")
        for g in sorted(set(c["by_group_um2"]) | set(r["by_group_um2"])):
            print(f"  {g:11s} {c['by_group_um2'].get(g, 0) - r['by_group_um2'].get(g, 0):+10.1f}")
        ms = set(c["by_master"]) | set(r["by_master"])
        rows = []
        for m in ms:
            d = c["by_master"].get(m, 0) - r["by_master"].get(m, 0)
            if d:
                rows.append((d * areas[PFX + m], m, d))
        for a, m, d in sorted(rows):
            print(f"    {m:12s} {d:+4d}  {a:+8.1f}")
        c["delta_vs_ref"] = {"ref": ref, "total_um2": round(c["total_um2"] - r["total_um2"], 3)}
    if out:
        json.dump(c, open(out, "w"), indent=1)


if __name__ == "__main__":
    main()
