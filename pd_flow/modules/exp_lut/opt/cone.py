#!/usr/bin/env python3
"""cone.py <netlist.v> ... : in-context exp_lut logic in a shipped-flow chip netlist.

exp_lut has no flops and its W outputs are not named after flattening, so its cone is found
from its inputs instead (forward closure):
  I   = the S-register outputs (nets core.exponent_unit.D[*]) and the shift config flops
        (config_chain[7:4]);
  F   = every cell all of whose inputs are in I, tie nets or outputs of F cells
        (logic that is a pure function of exp_lut's inputs);
  sh  = cells of F with a shift net in their transitive fan-in (only exp_lut reads score_shift
        combinationally, so these are exp_lut's by construction);
  exp = sh plus the D-only cells of F whose every load is in exp (D-only decode used solely by
        exp_lut), iterated to a fixed point.
'exp' is the in-context exp_lut area; rest = chip - exp. D-only cells of F that also feed the
adder or the max_reg compare are reported separately as 'shared'. Cells that merge W with
mac_unit signals (x mux, L adder) have non-exp inputs and land in 'rest' by construction.
"""
import re, sys, json
LIB = ("/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/"
       "gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib")
area = {}; cur = None
for line in open(LIB):
    m = re.match(r'\s*cell\s*\(\s*"?gf180mcu_fd_sc_mcu7t5v0__(\w+)"?\s*\)', line)
    if m: cur = m.group(1)
    m = re.match(r'\s*area\s*:\s*([\d.]+)', line)
    if m and cur and cur not in area: area[cur] = float(m.group(1))
OUT = {"Z", "ZN", "Q"}
SHIFT = {f"\\config_chain[{i}]" for i in range(4, 8)}


def parse(fn):
    txt = open(fn).read()
    cells = {}
    for m in re.finditer(r'gf180mcu_fd_sc_mcu7t5v0__(\w+)\s+(\S+)\s*\((.*?)\);', txt, re.S):
        t, n, body = m.groups()
        pins = {p: net.strip() for p, net in re.findall(r'\.(\w+)\s*\(\s*([^()]*?)\s*\)', body)}
        cells[n] = (t, pins)
    return cells


def analyse(fn):
    cells = parse(fn)
    drv, loads = {}, {}
    for n, (t, pins) in cells.items():
        for p, net in pins.items():
            if p in OUT: drv[net] = n
            else: loads.setdefault(net, []).append(n)
    dnets = {net for net in drv if net.startswith("\\core.exponent_unit.D[")}
    assert len(dnets) == 22, len(dnets)
    ties = {net for net, c in drv.items() if cells[c][0].startswith("tie")}
    ties |= {"1'h0", "1'h1", "1'b0", "1'b1"}
    src = dnets | SHIFT | ties
    F, fout = set(), set()
    changed = True
    while changed:
        changed = False
        for n, (t, pins) in cells.items():
            if n in F or t.startswith(("dff", "tie", "fill", "tap", "endcap")): continue
            ins = [v for p, v in pins.items() if p not in OUT]
            if ins and all(v in src or v in fout for v in ins):
                F.add(n); changed = True
                fout |= {v for p, v in pins.items() if p in OUT}
    # shift dependence
    shdep = {}
    def dep(c):
        if c in shdep: return shdep[c]
        shdep[c] = False
        r = False
        for p, v in cells[c][1].items():
            if p in OUT: continue
            if v in SHIFT: r = True
            elif v in drv and drv[v] in F and dep(drv[v]): r = True
        shdep[c] = r
        return r
    sh = {c for c in F if dep(c)}
    exp = set(sh); changed = True
    while changed:
        changed = False
        for c in F - exp:
            outs = [v for p, v in cells[c][1].items() if p in OUT]
            ls = [l for o in outs for l in loads.get(o, [])]
            if ls and all(l in exp for l in ls):
                exp.add(c); changed = True
    shared = F - exp
    A = lambda s: sum(area[cells[c][0]] for c in s)
    total = sum(area[t] for t, _ in cells.values())
    # W frontier: exp cells driving something outside exp
    front = [c for c in exp if any(l not in exp for p, v in cells[c][1].items() if p in OUT
                                   for l in loads.get(v, []))]
    hist = {}
    for c in exp: hist[cells[c][0]] = hist.get(cells[c][0], 0) + 1
    return {"netlist": fn.split("/")[-1], "chip_area": round(total, 4), "cells": len(cells),
            "exp_cells": len(exp), "exp_area": round(A(exp), 4),
            "shared_dOnly_cells": len(shared), "shared_dOnly_area": round(A(shared), 4),
            "frontier_cells": len(front), "rest_area": round(total - A(exp), 4), "exp_hist": hist}


if __name__ == "__main__":
    js = "--json" in sys.argv
    res = [analyse(f) for f in sys.argv[1:] if f != "--json"]
    for r in res:
        if js: print(json.dumps(r))
        else:
            print(f"{r['netlist']:28s} chip={r['chip_area']:10.1f} exp={r['exp_cells']:3d}/{r['exp_area']:7.1f} "
                  f"shared={r['shared_dOnly_cells']:2d}/{r['shared_dOnly_area']:6.1f} front={r['frontier_cells']:2d} "
                  f"rest={r['rest_area']:9.1f}  " + " ".join(f"{k}:{v}" for k, v in sorted(r['exp_hist'].items())))
