#!/usr/bin/env python3
"""Resized and inserted instances of a LibreLane netlist against a reference netlist.

usage: upsize_diff.py <reference.nl.v> <netlist.nl.v> [--json out.json] [-q]
Resized  : same instance name, different master (logic group, census.py naming)
Inserted : instance names absent from the reference, by census group and master
Removed  : reference instance names absent from the netlist
Each resized instance is listed with its area delta, the net its output drives and that net's
fanout in the netlist. Areas are LEF SIZE products.
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))
import census  # noqa: E402

PFX = census.PFX
INST_RE = re.compile(r"^\s*(" + PFX + r"\S+)\s+(\\?\S+)\s*\((.*?)\);", re.M | re.S)
CONN_RE = re.compile(r"\.(\w+)\(\s*(\\?[^()]*?)\s*\)")
OUT_PINS = {"Z", "ZN", "Q", "CO", "S"}


def parse(path):
    insts, loads = {}, Counter()
    for m in INST_RE.finditer(open(path).read()):
        master, name, body = m.group(1)[len(PFX):], m.group(2), m.group(3)
        outs = []
        for p, n in CONN_RE.findall(body):
            n = n.strip()
            if p in OUT_PINS:
                outs.append(n)
            else:
                loads[n] += 1
        insts[name] = (master, outs)
    return insts, loads


def diff(ref, nl):
    areas = {k[len(PFX):]: v for k, v in census.lef_areas().items()}
    r, _ = parse(ref)
    n, loads = parse(nl)
    resized = []
    for name, (m, outs) in n.items():
        if name in r and r[name][0] != m:
            m0 = r[name][0]
            resized.append({"inst": name, "from": m0, "to": m, "delta_um2": round(areas[m] - areas[m0], 3),
                            "net": outs[0] if outs else None, "fanout": loads.get(outs[0], 0) if outs else 0})
    resized.sort(key=lambda x: -x["delta_um2"])
    ins = defaultdict(Counter)
    ins_area = defaultdict(float)
    for name, (m, _) in n.items():
        if name not in r:
            g = census.group(PFX + m, name)
            if m.startswith(("fill_", "fillcap")):
                continue
            ins[g][m] += 1
            ins_area[g] += areas[m]
    removed = Counter(r[name][0] for name in r if name not in n)
    by_pair = Counter((x["from"], x["to"]) for x in resized)
    pair_area = defaultdict(float)
    for x in resized:
        pair_area[(x["from"], x["to"])] += x["delta_um2"]
    return {
        "reference": ref, "netlist": nl,
        "resized_count": len(resized),
        "resized_um2": round(sum(x["delta_um2"] for x in resized), 3),
        "resized_by_pair": [{"from": a, "to": b, "count": c, "delta_um2": round(pair_area[(a, b)], 3)}
                            for (a, b), c in sorted(by_pair.items(), key=lambda kv: -pair_area[kv[0]])],
        "resized": resized,
        "inserted_by_group_um2": {g: round(v, 3) for g, v in sorted(ins_area.items())},
        "inserted_by_group_master": {g: dict(sorted(c.items())) for g, c in sorted(ins.items())},
        "removed_by_master": dict(sorted(removed.items())),
    }


def main():
    a = sys.argv[1:]
    out = None
    if "--json" in a:
        i = a.index("--json"); out = a[i + 1]; del a[i:i + 2]
    quiet = "-q" in a
    a = [x for x in a if x != "-q"]
    d = diff(a[0], a[1])
    print(f"resized {d['resized_count']} instances, {d['resized_um2']:+.1f} um2")
    for p in d["resized_by_pair"]:
        print(f"  {p['from']:>10s} -> {p['to']:<10s} x{p['count']:<3d} {p['delta_um2']:+7.1f}")
    if not quiet:
        for x in d["resized"]:
            print(f"    {x['inst']:10s} {x['from']:>10s} -> {x['to']:<10s} {x['delta_um2']:+6.1f}  net {x['net']} fanout {x['fanout']}")
    print("inserted:", d["inserted_by_group_um2"])
    for g, c in d["inserted_by_group_master"].items():
        print(f"  {g:10s} {c}")
    print("removed:", d["removed_by_master"])
    if out:
        json.dump(d, open(out, "w"), indent=1)


if __name__ == "__main__":
    main()
