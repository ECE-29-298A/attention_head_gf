#!/usr/bin/env python3
"""Collect every mux2_1 DRC result under the DRC work root into one JSON and a Markdown table.

usage: collect_drc.py <drc root, e.g. /Users/samuelzhang/ttharden/md_drc> <out.json>
Layout sets: <root> (single cells, abutted rows, neighbour pairs, positive controls), <root>/tblock
(routed LibreLane test block) and <root>/chip (final chip GDS). Tools, by directory:
  magic          Magic 8.3.623, PDK 54435919 tech, drc(full), euclidean  (*.magic.rpt "COUNT n")
  klayout_a      PDK 54435919 KLayout deck gf180mcu.drc, feol+beol+offgrid, deep
  klayout_b_conn the same with conn_drc=true (connectivity rules)
  ttdeck         TT precheck deck (PDK e8daeda7 gf180mcu.drc, variant gf180mcuD, deep):
                 <name>.drc  = decks all,-density,-antenna ; <name>.antenna = decks antenna
"""
import glob
import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter


def lyrdb(p):
    cnt = Counter()
    for it in ET.parse(p).getroot().iter("item"):
        cnt[(it.findtext("category") or "?").strip("'")] += 1
    return {"total": sum(cnt.values()), "by_rule": dict(sorted(cnt.items()))}


def magic(p):
    txt = open(p).read()
    n = sum(int(x) for x in re.findall(r"COUNT:?\s*(\d+)", txt))
    rules = Counter(l.strip() for l in txt.splitlines() if "(" in l and ")" in l and "COUNT" not in l)
    return {"total": n, "by_rule": dict(rules)}


def collect(d):
    out = {}
    for f in sorted(glob.glob(os.path.join(d, "magic", "*.magic.rpt"))):
        out.setdefault(os.path.basename(f)[:-len(".magic.rpt")], {})["magic"] = magic(f)
    for tool in ("klayout_a", "klayout_b_conn"):
        for f in sorted(glob.glob(os.path.join(d, tool, "*.lyrdb"))):
            out.setdefault(os.path.basename(f)[:-6], {})[tool] = lyrdb(f)
    for f in sorted(glob.glob(os.path.join(d, "ttdeck", "*.lyrdb"))):
        b = os.path.basename(f)[:-6]
        name, kind = b.rsplit(".", 1)
        out.setdefault(name, {})["ttdeck_" + kind] = lyrdb(f)
    gds = {os.path.basename(g)[:-4]: hashlib.sha256(open(g, "rb").read()).hexdigest()
           for g in glob.glob(os.path.join(d, "gds", "*.gds"))}
    for k, v in out.items():
        if k in gds:
            v["gds_sha256"] = gds[k]
    return out


def main():
    root, outp = sys.argv[1], sys.argv[2]
    res = {"cells": collect(root), "tblock": collect(os.path.join(root, "tblock")),
           "chip": collect(os.path.join(root, "chip"))}
    json.dump(res, open(outp, "w"), indent=1)
    tools = ["magic", "klayout_a", "klayout_b_conn", "ttdeck_drc", "ttdeck_antenna"]
    print("| set | layout | " + " | ".join(tools) + " |")
    print("|---|---|" + "---|" * len(tools))
    for s, layouts in res.items():
        for name, r in layouts.items():
            cells = []
            for t in tools:
                if t not in r:
                    cells.append("-")
                    continue
                x = r[t]
                cells.append(str(x["total"]) + ("" if not x["total"] else " (" + ", ".join(f"{k} {v}" for k, v in x["by_rule"].items()) + ")"))
            print(f"| {s} | {name} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
