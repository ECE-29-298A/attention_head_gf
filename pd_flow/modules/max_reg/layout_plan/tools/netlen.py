#!/usr/bin/env python3
"""netlen.py <tag>=<run_dir_with def/ and pnl/> ... : routed wire length (DEF ROUTED/NEW segment Manhattan
sum, um) split into classes, to attribute a chip wirelength change:
  maxreg   nets with a pin on an M flop, an S flop (mac_unit S register), a max_reg exclusive-cone cell
           (cone.py definition, recomputed per run) or a fixed block cell (core.max_unit.*)
  clock    nets named clk* / clknet*
  rest     everything else
Adapted from ripple_add/layout_review/netlen.py (segment parser) and opt/cone.py (cone)."""
import json, os, re, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
OUT = {"Z", "ZN", "Q"}
def netlens(path):
    t = open(path).read()
    dbu = int(re.search(r"UNITS DISTANCE MICRONS (\d+)", t).group(1))
    sec = re.search(r'^NETS \d+ ;(.*?)^END NETS', t, re.S | re.M).group(1)
    out = {}
    for blk in re.split(r'\n\s*- ', sec):
        m = re.match(r'(\S+)', blk.strip())
        if not m: continue
        name = m[1].replace('\\', '')
        pins = re.findall(r'\( (\S+) (\S+) \)', blk.split('+')[0])
        L = 0.0
        for seg in re.finditer(r'(?:ROUTED|NEW) (Metal\d)\s+(?:\d+\s+)?(?:\+ \S+ )*\( (\d+) (\d+)(?: \d+)? \) \( (\*|\d+) (\*|\d+)(?: \d+)? \)', blk):
            x1, y1 = int(seg[2]), int(seg[3]); x2 = x1 if seg[4] == '*' else int(seg[4]); y2 = y1 if seg[5] == '*' else int(seg[5])
            L += (abs(x2 - x1) + abs(y2 - y1)) / dbu
        out[name] = (L, [p[0].replace('\\', '') for p in pins])
    return out
def parse(fn):
    cells = {}
    for m in re.finditer(r'gf180mcu_fd_sc_mcu7t5v0__(\w+)\s+(\S+)\s*\((.*?)\);', open(fn).read(), re.S):
        t, n, body = m.groups()
        cells[n.lstrip("\\")] = (t, {p: net.strip().lstrip("\\").strip() for p, net in re.findall(r'\.(\w+)\s*\(\s*([^()]*?)\s*\)', body)})
    return cells
def maxreg_cells(cells):
    drv, loads = {}, {}
    for n, (t, pins) in cells.items():
        for p, net in pins.items():
            (drv.__setitem__(net, n) if p in OUT else loads.setdefault(net, []).append(n))
    isff = lambda t: t.startswith(("dff", "sdff"))
    M = {n for n, (t, p) in cells.items() if isff(t) and re.fullmatch(r'core\.mac\.M\[\d+\]', p.get("Q", ""))}
    S = {n for n, (t, p) in cells.items() if isff(t) and re.fullmatch(r'core\.exponent_unit\.D\[\d+\]', p.get("Q", ""))}
    blk = {n for n in cells if n.startswith("core.max_unit.")}
    cone = set(); stack = [cells[n][1].get("D") for n in M] + [cells[n][1].get("SE") for n in M if cells[n][1].get("SE")]
    while stack:
        net = stack.pop(); c = drv.get(net)
        if c is None or c in cone: continue
        t, pins = cells[c]
        if isff(t) or t.startswith("tie"): continue
        cone.add(c); stack += [v for p, v in pins.items() if p not in OUT]
    excl = set(cone); ch = True
    while ch:
        ch = False
        for c in list(excl):
            outs = [v for p, v in cells[c][1].items() if p in OUT]
            if any(l not in excl and l not in M for o in outs for l in loads.get(o, [])):
                excl.discard(c); ch = True
    return M | S | blk | excl, {"M": len(M), "S": len(S), "block": len(blk), "excl_cone": len(excl)}
res = {}
for arg in sys.argv[1:]:
    tag, d = arg.split("=", 1)
    deff = [os.path.join(d, "def", f) for f in os.listdir(os.path.join(d, "def"))][0]
    pnl = [os.path.join(d, "pnl", f) for f in os.listdir(os.path.join(d, "pnl"))][0]
    nl = netlens(deff); cells = parse(pnl); mr, cnt = maxreg_cells(cells)
    cls = collections.Counter()
    for name, (L, pins) in nl.items():
        if name.startswith(("clk", "clknet")): cls["clock"] += L
        elif any(p.replace('\\', '') in mr for p in pins): cls["maxreg"] += L
        else: cls["rest"] += L
    cls["total"] = sum(v for k, v in cls.items())
    res[tag] = {"def": deff, "counts": cnt, **{k: round(v, 1) for k, v in cls.items()}}
    print(f"{tag:10s} total {cls['total']:9.1f}  maxreg {cls['maxreg']:8.1f}  clock {cls['clock']:7.1f}  rest {cls['rest']:9.1f}  {cnt}")
if "--json" in os.environ.get("NETLEN_JSON", ""): pass
json.dump(res, open(os.environ.get("NETLEN_OUT", "/dev/null"), "w"), indent=1)
