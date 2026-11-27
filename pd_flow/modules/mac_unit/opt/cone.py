#!/usr/bin/env python3
"""cone.py [--json] <netlist.v>... : in-context mac_unit cone of a flat shipped-flow (x0) chip netlist.

Flop groups by Q net, same rule as chip_partition/scripts/attrib.py:
  MAC flops = S (Q alias core.exponent_unit.D[*]), ring (core.mac.ring[*], core.divider_unit.sum_in[*],
              core.divider_unit.magnitude[0]), L (core.divider_unit.denominator[*]); fallback for renamed
              candidate state: core.mac.<x> other than the neighbours' aliases (M, qi, ki, sel, subtract,
              accum_en), core.score/o0/weight_sum.  Must total 194 at OUTPUTS=8 (checked).
  DEST(c) = flop groups / PO reached from comb cell c; SRC(c) = flop groups / PI in its fan-in.
  mac    = MAC flops + comb cells with DEST == {MAC}, minus the exp_lut refinement
  exp    = comb cells with DEST == {MAC} and SRC <= {MAC_S, FE_shift} (exp_lut's table; attrib.py rule)
  shared = comb cells whose DEST contains MAC and something else
  rest   = chip - mac - exp - shared
Areas from the Liberty tt file (sum is a constant ~79 um2 above stat.json; stat.json is the judge).
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
GROUPS = [
    (r"^config_chain\[[4-7]\]$", "FE_shift"),
    (r"^(config_chain|sck_sync|cs_sync)\[", "FE"),
    (r"^core\.exponent_unit\.D\[|^core\.score\[", "MAC_S"),
    (r"^core\.mac\.ring\[|^core\.divider_unit\.sum_in\[|^core\.divider_unit\.magnitude\[0\]$|^core\.o0\[", "MAC_RING"),
    (r"^core\.divider_unit\.denominator\[|^core\.weight_sum\[", "MAC_L"),
    (r"^core\.mac\.(M|qi|ki|sel|subtract|accum_en|load|first|score_en|W|v|bit_sel|accum_mode)(\[|$)", "OTHER"),
    (r"^core\.mac\.", "MAC_X"),
    (r".", "OTHER"),
]
def group(q):
    q = q.lstrip('\\').strip()
    for rx, g in GROUPS:
        if re.search(rx, q): return g

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
    sys.setrecursionlimit(100000)
    txt, cells, pouts = parse(fn)
    isff = lambda t: t.startswith(("dff", "sdff", "lat", "icg"))
    drv, loads = {}, {}
    for n, (t, pins) in cells.items():
        for p, net in pins.items():
            if not net: continue
            if p in outp[t]: drv[net] = n
            else: loads.setdefault(net, []).append(n)
    grp = {}
    for n, (t, pins) in cells.items():
        if isff(t):
            q = pins.get("Q") or pins.get("GCLK") or ""
            grp[n] = group(q)
    ismac = lambda g: g.startswith("MAC")
    dest, src = {}, {}
    def D(c):
        if c in dest: return dest[c]
        dest[c] = set(); s = set()
        t, pins = cells[c]
        for p, net in pins.items():
            if p not in outp[t]: continue
            if re.sub(r'\[\d+\]$', '', net.lstrip('\\')) in pouts: s.add("PO")
            for l in loads.get(net, []):
                s |= {"MAC" if ismac(grp[l]) else grp[l]} if l in grp else D(l)
        dest[c] = s; return s
    def S(c):
        if c in src: return src[c]
        src[c] = set(); s = set()
        t, pins = cells[c]
        for p, net in pins.items():
            if p in outp[t] or not net: continue
            d = drv.get(net)
            if d is None: s.add("PI")
            elif d in grp: s.add(grp[d])
            else: s |= S(d)
        src[c] = s; return s
    mac, exp, shared = set(), set(), set()
    for c, (t, _) in cells.items():
        if c in grp:
            if ismac(grp[c]): mac.add(c)
            continue
        if t.startswith(("tie", "fill", "tap", "endcap")): continue
        d = D(c)
        if d == {"MAC"}:
            (exp if S(c) <= {"MAC_S", "FE_shift"} else mac).add(c)
        elif "MAC" in d: shared.add(c)
    A = lambda s: sum(area[cells[c][0]] for c in s)
    total = sum(area[t] for t, _ in cells.values())
    hist = {}
    for c in mac: hist[cells[c][0]] = hist.get(cells[c][0], 0) + 1
    ffs = [c for c in mac if c in grp]
    fg = {}
    for c in ffs: fg[grp[c]] = fg.get(grp[c], 0) + 1
    return {"netlist": fn.split("/")[-1], "sha": hashlib.sha256(txt.encode()).hexdigest(),
            "chip_area": round(total, 4), "cells": len(cells),
            "mac_cells": len(mac), "mac_area": round(A(mac), 4), "mac_flops": len(ffs), "mac_flop_groups": fg,
            "mac_flop_area": round(A(ffs), 4), "mac_logic_area": round(A(mac) - A(ffs), 4),
            "exp_cells": len(exp), "exp_area": round(A(exp), 4),
            "shared_cells": len(shared), "shared_area": round(A(shared), 4),
            "rest_area": round(total - A(mac) - A(exp) - A(shared), 4), "mac_hist": dict(sorted(hist.items()))}

if __name__ == "__main__":
    js = "--json" in sys.argv
    for f in sys.argv[1:]:
        if f == "--json": continue
        r = analyse(f)
        if js: print(json.dumps(r))
        else:
            print(f"{r['netlist']:30s} chip={r['chip_area']:10.1f} mac={r['mac_cells']:3d}/{r['mac_area']:8.1f} "
                  f"(ff {r['mac_flops']}/{r['mac_flop_area']:.1f} {r['mac_flop_groups']}) exp={r['exp_area']:.1f} "
                  f"shared={r['shared_cells']}/{r['shared_area']:.1f} rest={r['rest_area']:9.1f}")
