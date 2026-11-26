#!/usr/bin/env python3
"""cone.py <netlist.v> ... : in-context max_reg logic in a shipped-flow chip netlist.
The 22 M flops are the dffq cells whose Q drives core.mac.M[*] (the max_reg output). The cone is
the transitive fan-in of their D pins, stopped at flop outputs, tie cells and ports.
'excl' counts only cone cells all of whose fanout stays inside the cone + M flops (logic that
would disappear with max_reg); 'cone' counts everything in the fan-in (includes shared decode)."""
import re, sys
LIB = ("/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/"
       "gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib")
area = {}; cur = None
for line in open(LIB):
    m = re.match(r'\s*cell\s*\(\s*"?gf180mcu_fd_sc_mcu7t5v0__(\w+)"?\s*\)', line)
    if m: cur = m.group(1)
    m = re.match(r'\s*area\s*:\s*([\d.]+)', line)
    if m and cur and cur not in area: area[cur] = float(m.group(1))
OUT = {"Z", "ZN", "Q"}
def parse(fn):
    txt = open(fn).read()
    cells = {}
    for m in re.finditer(r'gf180mcu_fd_sc_mcu7t5v0__(\w+)\s+(\S+)\s*\((.*?)\);', txt, re.S):
        t, n, body = m.groups()
        pins = {p: net.strip() for p, net in re.findall(r'\.(\w+)\s*\(\s*([^()]*?)\s*\)', body)}
        cells[n] = (t, pins)
    return cells
for fn in sys.argv[1:]:
    cells = parse(fn)
    drv = {}; loads = {}
    for n, (t, pins) in cells.items():
        for p, net in pins.items():
            if p in OUT: drv[net] = n
            else: loads.setdefault(net, []).append(n)
    mff = [n for n, (t, p) in cells.items() if t.startswith("dff") and re.search(r'core\.mac\.M\[', p.get("Q", ""))]
    cone = set(); stack = [cells[n][1]["D"] for n in mff]
    while stack:
        net = stack.pop(); c = drv.get(net)
        if c is None or c in cone: continue
        t, pins = cells[c]
        if t.startswith(("dff", "tie")): continue
        cone.add(c)
        stack += [v for p, v in pins.items() if p not in OUT]
    keep = cone | set(mff)
    excl = set(cone); changed = True
    while changed:
        changed = False
        for c in list(excl):
            outs = [v for p, v in cells[c][1].items() if p in OUT]
            if any(l not in excl and l not in mff for o in outs for l in loads.get(o, [])):
                excl.discard(c); changed = True
    A = lambda s: sum(area[cells[c][0]] for c in s)
    hist = {}
    for c in excl: hist[cells[c][0]] = hist.get(cells[c][0], 0) + 1
    print(f"{fn.split('/')[-1]:28s} Mflops={len(mff)} flopA={A(mff):8.1f} cone={len(cone):3d}/{A(cone):7.1f} "
          f"excl={len(excl):3d}/{A(excl):7.1f} max_reg_total={A(mff)+A(excl):.1f}  "
          + " ".join(f"{k}:{v}" for k, v in sorted(hist.items())))
