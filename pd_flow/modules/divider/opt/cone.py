#!/usr/bin/env python3
"""cone.py [--json] <netlist.v>... : in-context divider cone of a flat shipped-flow chip netlist.

Same rule as the architects' attribution (chip_partition/scripts/attrib.py):
  DIV flops  = flops whose Q net is core.divider_unit.* or core.div_done, except the MAC-owned
               input registers core.divider_unit.sum_in[*], .denominator[*] and the ring-head alias
               .magnitude[0] (= sum_in[0]).
  DEST(c)    = set of flop groups {DIV, other} (and PO) reached from comb cell c's outputs through
               combinational logic.
  div        = DIV flops + comb cells with DEST == {DIV}
  shared     = comb cells whose DEST contains DIV and something else
  rest       = chip - div - shared
Pin directions from the Liberty file. Tie cells count as rest.
"""
import re, sys, json, hashlib
LIB = ("/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/"
       "gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib")
area, outp = {}, {}
cur = None; pin = None
for line in open(LIB):
    m = re.match(r'\s*cell\s*\(\s*"?gf180mcu_fd_sc_mcu7t5v0__(\w+)"?\s*\)', line)
    if m: cur = m.group(1); outp[cur] = set(); continue
    m = re.match(r'\s*area\s*:\s*([\d.]+)', line)
    if m and cur and cur not in area: area[cur] = float(m.group(1))
    m = re.match(r'\s*pin\s*\(\s*"?(\w+)"?\s*\)', line)
    if m: pin = m.group(1)
    m = re.match(r'\s*direction\s*:\s*"?(\w+)"?', line)
    if m and cur and pin and m.group(1) == "output": outp[cur].add(pin)
EXCL = re.compile(r'^\\?core\.divider_unit\.(sum_in\[|denominator\[|magnitude\[0\])')
DIVRX = re.compile(r'^\\?core\.(divider_unit\.|div_done$)')


def parse(fn):
    txt = open(fn).read()
    cells = {}
    for m in re.finditer(r'gf180mcu_fd_sc_mcu7t5v0__(\w+)\s+(\S+)\s*\((.*?)\);', txt, re.S):
        t, n, body = m.groups()
        pins = {p: net.strip() for p, net in re.findall(r'\.(\w+)\s*\(\s*([^()]*?)\s*\)', body)}
        cells[n] = (t, pins)
    outs = set()
    for m in re.finditer(r'^\s*output\s+(?:\[[^\]]*\]\s*)?(\S+?)\s*;', txt, re.M):
        outs.add(m.group(1))
    return txt, cells, outs


def analyse(fn):
    txt, cells, pouts = parse(fn)
    isff = lambda t: t.startswith(("dff", "sdff"))
    drv, loads = {}, {}
    for n, (t, pins) in cells.items():
        for p, net in pins.items():
            if not net: continue
            if p in outp[t]: drv[net] = n
            else: loads.setdefault(net, []).append(n)
    grp = {}
    for n, (t, pins) in cells.items():
        if isff(t):
            q = pins["Q"]
            grp[n] = "DIV" if DIVRX.search(q) and not EXCL.search(q) else "other"
    dest = {}
    def D(c):
        if c in dest: return dest[c]
        dest[c] = set(); s = set()
        t, pins = cells[c]
        for p, net in pins.items():
            if p not in outp[t]: continue
            if re.sub(r'\[\d+\]$', '', net.lstrip('\\')) in pouts: s.add("PO")
            for l in loads.get(net, []):
                s |= {grp[l]} if l in grp else D(l)
        dest[c] = s; return s
    div, shared = set(), set()
    for c, (t, _) in cells.items():
        if c in grp:
            if grp[c] == "DIV": div.add(c)
            continue
        if t.startswith(("tie", "fill", "tap", "endcap")): continue
        d = D(c)
        if d == {"DIV"}: div.add(c)
        elif "DIV" in d: shared.add(c)
    A = lambda s: sum(area[cells[c][0]] for c in s)
    total = sum(area[t] for t, _ in cells.values())
    hist = {}
    for c in div: hist[cells[c][0]] = hist.get(cells[c][0], 0) + 1
    ffs = [c for c in div if c in grp]
    return {"netlist": fn.split("/")[-1], "sha": hashlib.sha256(txt.encode()).hexdigest(),
            "chip_area": round(total, 4), "cells": len(cells),
            "div_cells": len(div), "div_area": round(A(div), 4), "div_flops": len(ffs),
            "div_flop_area": round(A(ffs), 4), "div_logic_area": round(A(div) - A(ffs), 4),
            "shared_cells": len(shared), "shared_area": round(A(shared), 4),
            "rest_area": round(total - A(div) - A(shared), 4), "div_hist": dict(sorted(hist.items()))}


if __name__ == "__main__":
    js = "--json" in sys.argv
    for f in sys.argv[1:]:
        if f == "--json": continue
        r = analyse(f)
        if js: print(json.dumps(r))
        else:
            print(f"{r['netlist']:30s} chip={r['chip_area']:10.1f} div={r['div_cells']:3d}/{r['div_area']:7.1f} "
                  f"(ff {r['div_flops']}/{r['div_flop_area']:.1f}) shared={r['shared_cells']}/{r['shared_area']:.1f} "
                  f"rest={r['rest_area']:9.1f}")
