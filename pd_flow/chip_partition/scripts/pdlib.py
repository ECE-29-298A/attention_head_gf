#!/usr/bin/env python3
"""Shared parsers for the chip-partition analysis (Architect A, pd_flow/chip_partition).

- liberty_areas(): cell -> area from the FULL 7-track TT liberty (not the h2-restricted one,
  whose missing buf_2 etc. make Yosys stat under-count; see README "area accounting").
- lef_macros(): master -> (width, height, class, pins) from the PDK LEF.
- parse_netlist(): Yosys-written gate-level Verilog (flat or hierarchical) -> modules.
- parse_def(): DEF components, pins, rows and routed net lengths.
All coordinates in um. No estimates are made here.
"""
import re, os, hashlib

PDK = ("/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/"
       "54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD")
LIB = PDK + "/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib"
LEF = PDK + "/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lef/gf180mcu_fd_sc_mcu7t5v0.lef"
PFX = "gf180mcu_fd_sc_mcu7t5v0__"
SITE_W, ROW_H = 0.56, 3.92


def sha(path, n=16):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:n]


_AREA = None


def liberty_areas():
    global _AREA
    if _AREA is None:
        _AREA, cur = {}, None
        for line in open(LIB):
            m = re.match(r'\s*cell\s*\(\s*"?(\w+)"?\s*\)', line)
            if m:
                cur = m.group(1)
            m = re.match(r'\s*area\s*:\s*([\d.]+)', line)
            if m and cur and cur not in _AREA:
                _AREA[cur] = float(m.group(1))
    return _AREA


_LEF = None


def lef_macros():
    """master -> dict(w, h, cls, pins={pin: [(layer, x0, y0, x1, y1), ...]}, dir={pin: dir})"""
    global _LEF
    if _LEF is not None:
        return _LEF
    _LEF = {}
    cur = pin = layer = None
    for line in open(LEF):
        t = line.split()
        if not t:
            continue
        if t[0] == "MACRO":
            cur = {"w": 0, "h": 0, "cls": "", "pins": {}, "dir": {}, "use": {}}
            _LEF[t[1]] = cur
            name = t[1]
        elif cur is None:
            continue
        elif t[0] == "CLASS" and pin is None:
            cur["cls"] = " ".join(t[1:]).rstrip(" ;")
        elif t[0] == "SIZE":
            cur["w"], cur["h"] = float(t[1]), float(t[3])
        elif t[0] == "PIN":
            pin = t[1]
            cur["pins"][pin] = []
        elif t[0] == "DIRECTION" and pin:
            cur["dir"][pin] = t[1]
        elif t[0] == "USE" and pin:
            cur["use"][pin] = t[1]
        elif t[0] == "LAYER" and pin:
            layer = t[1]
        elif t[0] == "RECT" and pin and layer:
            cur["pins"][pin].append((layer,) + tuple(float(v) for v in t[1:5]))
        elif t[0] == "END" and len(t) > 1:
            if pin and t[1] == pin:
                pin = layer = None
            elif t[1] == name:
                cur = None
    return _LEF


# ----------------------------------------------------------------------------- Verilog netlist
_TOK = re.compile(r"\\\S+|[A-Za-z_][A-Za-z0-9_$]*|\d+'[bBhHdDoO][0-9a-fA-FxXzZ_]+|\d+|\S")


def _tokens(txt):
    txt = re.sub(r"/\*.*?\*/", " ", txt, flags=re.S)
    txt = re.sub(r"(?<!\\)//[^\n]*", " ", txt)
    txt = re.sub(r"\(\*.*?\*\)", " ", txt, flags=re.S)
    return _TOK.findall(txt)


def _clean(name):
    return name[1:] if name.startswith("\\") else name


def _const_bits(tok):
    m = re.match(r"(\d+)'([bBhHdDoO])([0-9a-fA-FxXzZ_]+)", tok)
    w, base, digits = int(m.group(1)), m.group(2).lower(), m.group(3).replace("_", "")
    if base == "b":
        bits = digits
    elif base == "h":
        bits = "".join(f"{int(c, 16):04b}" if c not in "xXzZ" else c * 4 for c in digits)
    elif base == "o":
        bits = "".join(f"{int(c, 8):03b}" for c in digits)
    else:
        bits = bin(int(digits))[2:]
    bits = bits.rjust(w, "0")[-w:]
    return [f"1'b{b}" for b in bits]  # MSB first


class Module:
    def __init__(self, name):
        self.name = name
        self.ports = []          # (dir, name, msb, lsb) in declaration order
        self.wires = {}          # name -> (msb, lsb) or None for scalar
        self.insts = []          # (type, name, {pin: [bit nets, MSB first]})
        self.assigns = []        # (lhs bits, rhs bits)

    def width(self, name):
        r = self.wires.get(name)
        return 1 if r is None else abs(r[0] - r[1]) + 1

    def bits(self, name):
        r = self.wires.get(name)
        if r is None:
            return [name]
        step = -1 if r[0] >= r[1] else 1
        return [f"{name}[{i}]" for i in range(r[0], r[1] + step, step)]


def _parse_expr(toks, i, mod):
    """Parse a connection expression starting at toks[i]; returns (bits MSB first, next i)."""
    t = toks[i]
    if t == "{":
        bits, i = [], i + 1
        while toks[i] != "}":
            b, i = _parse_expr(toks, i, mod)
            bits += b
            if toks[i] == ",":
                i += 1
        return bits, i + 1
    if re.match(r"\d+'", t):
        return _const_bits(t), i + 1
    name = _clean(t)
    i += 1
    if i < len(toks) and toks[i] == "[":
        a = int(toks[i + 1])
        if toks[i + 2] == ":":
            b = int(toks[i + 3])
            step = -1 if a >= b else 1
            return [f"{name}[{k}]" for k in range(a, b + step, step)], i + 5
        return [f"{name}[{a}]"], i + 3
    return mod.bits(name), i


def parse_netlist(path):
    toks = _tokens(open(path).read())
    mods, i, n = {}, 0, len(toks)
    while i < n:
        if toks[i] != "module":
            i += 1
            continue
        mod = Module(_clean(toks[i + 1]))
        mods[mod.name] = mod
        i += 2
        while toks[i] != ";":
            i += 1
        i += 1
        pending = []
        while toks[i] != "endmodule":
            t = toks[i]
            if t in ("input", "output", "inout", "wire", "reg"):
                kind, i = t, i + 1
                rng = None
                if toks[i] == "[":
                    rng = (int(toks[i + 1]), int(toks[i + 3]))
                    i += 5
                while True:
                    nm = _clean(toks[i])
                    mod.wires[nm] = rng
                    if kind != "wire" and kind != "reg":
                        mod.ports.append((kind, nm) + (rng if rng else (None, None)))
                    i += 1
                    if toks[i] == ",":
                        i += 1
                        continue
                    break
                i += 1  # ';'
            elif t == "assign":
                lhs, i = _parse_expr(toks, i + 1, mod)
                assert toks[i] == "=", (path, toks[i - 3:i + 3])
                rhs, i = _parse_expr(toks, i + 1, mod)
                mod.assigns.append((lhs, rhs))
                i += 1
            else:
                typ, j = _clean(t), i + 1
                if toks[j] == "#":     # parameters (not expected in gate netlists)
                    depth, j = 0, j + 1
                    while True:
                        depth += toks[j] == "("
                        depth -= toks[j] == ")"
                        j += 1
                        if depth == 0:
                            break
                name = _clean(toks[j])
                j += 1
                assert toks[j] == "(", (path, typ, name, toks[j:j + 5])
                j += 1
                pins = {}
                while toks[j] != ")":
                    if toks[j] == ".":
                        pin = _clean(toks[j + 1])
                        assert toks[j + 2] == "("
                        if toks[j + 3] == ")":
                            pins[pin] = []
                            j += 4
                        else:
                            bits, j = _parse_expr(toks, j + 3, mod)
                            pins[pin] = bits
                            assert toks[j] == ")", (path, name, pin, toks[j:j + 4])
                            j += 1
                    elif toks[j] == ",":
                        j += 1
                    else:
                        raise ValueError(f"{path}: positional connections unsupported at {name}")
                pending.append((typ, name, pins))
                i = j + 2  # ')' ';'
        mod.insts = pending
        i += 1
    return mods


def top_module(mods):
    used = {typ for m in mods.values() for typ, _, _ in m.insts}
    tops = [m for m in mods if m not in used]
    assert len(tops) == 1, tops
    return tops[0]


def flatten_cells(mods, top=None):
    """Hierarchical netlist -> flat list of (path, master, {pin: net}) with nets named by
    hierarchical path; port nets of submodules are unified with the parent connection."""
    top = top or top_module(mods)
    out = []
    parent = {}

    def find(x):
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            # prefer constants, then shorter (higher-level) names as representative
            if rb.startswith("1'b") or (not ra.startswith("1'b") and len(rb) < len(ra)):
                ra, rb = rb, ra
            parent[rb] = ra

    def walk(mname, prefix):
        m = mods[mname]
        q = (lambda net: net if net.startswith("1'b") else prefix + net)
        for lhs, rhs in m.assigns:
            for a, b in zip(lhs, rhs):
                union(q(a), q(b))
        for typ, name, pins in m.insts:
            if typ in mods:
                sub = mods[typ]
                for pin, bits in pins.items():
                    for a, b in zip(sub.bits(pin), bits):
                        union(prefix + name + "." + a, q(b))
                walk(typ, prefix + name + ".")
            else:
                out.append((prefix + name, typ, {p: (q(b[0]) if b else None) for p, b in pins.items()},
                            prefix.rstrip(".")))
    walk(top, "")
    res = []
    for path, typ, pins, scope in out:
        res.append((path, typ, {p: (find(n) if n else None) for p, n in pins.items()}, scope))
    return res


# ----------------------------------------------------------------------------- DEF
def parse_def(path, want_routes=True):
    txt = open(path).read()
    unit = float(re.search(r"UNITS DISTANCE MICRONS (\d+)", txt).group(1))
    die = [float(v) / unit for v in re.search(
        r"DIEAREA \( (-?\d+) (-?\d+) \) \( (-?\d+) (-?\d+) \)", txt).groups()]
    rows = []
    for m in re.finditer(r"^ROW (\S+) (\S+) (\d+) (\d+) (\S+) DO (\d+) BY (\d+) STEP (\d+) (\d+)", txt, re.M):
        rows.append({"name": m.group(1), "x": int(m.group(3)) / unit, "y": int(m.group(4)) / unit,
                     "orient": m.group(5), "n": int(m.group(6)), "step": int(m.group(8)) / unit})
    comps = {}
    sec = txt[txt.index("\nCOMPONENTS"):txt.index("END COMPONENTS")]
    for st in sec.split(";")[1:]:
        m = re.search(r"-\s+(\S+)\s+(\S+)(.*)", st, re.S)
        if not m:
            continue
        name, master, rest = m.group(1), m.group(2), m.group(3)
        pm = re.search(r"\+\s+(PLACED|FIXED|COVER)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+(\S+)", rest)
        src = re.search(r"\+\s+SOURCE\s+(\S+)", rest)
        if pm:
            comps[name.replace("\\", "")] = {
                "master": master, "status": pm.group(1), "x": int(pm.group(2)) / unit,
                "y": int(pm.group(3)) / unit, "orient": pm.group(4),
                "source": src.group(1) if src else None}
        else:
            comps[name.replace("\\", "")] = {"master": master, "status": "UNPLACED", "x": None,
                                             "y": None, "orient": None, "source": None}
    pins = {}
    if "\nPINS" in txt:
        psec = txt[txt.index("\nPINS"):txt.index("END PINS")]
        for st in psec.split(";")[1:]:
            m = re.search(r"-\s+(\S+)\s+\+\s+NET\s+(\S+)", st)
            if not m:
                continue
            pl = re.search(r"\+\s+(PLACED|FIXED)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+(\S+)", st)
            ly = re.search(r"\+\s+LAYER\s+(\S+)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)", st)
            d = re.search(r"\+\s+DIRECTION\s+(\S+)", st)
            pins[m.group(1).replace("\\", "")] = {
                "net": m.group(2).replace("\\", ""),
                "x": int(pl.group(2)) / unit if pl else None, "y": int(pl.group(3)) / unit if pl else None,
                "layer": ly.group(1) if ly else None, "dir": d.group(1) if d else None}
    nets = {}
    if want_routes and "\nNETS" in txt:
        nsec = txt[txt.index("\nNETS"):txt.index("END NETS")]
        for st in nsec.split(";\n")[1:]:
            m = re.match(r"\s*-\s+(\S+)", st)
            if not m:
                continue
            name = m.group(1).replace("\\", "")
            conns = re.findall(r"\(\s*(\S+)\s+(\S+)\s*\)", st.split("+")[0])
            length = 0.0
            for seg in re.findall(r"(?:ROUTED|NEW)\s+(\S+)\s+(.*?)(?=\n\s*(?:NEW|\+|$)|$)", st, re.S):
                pts = re.findall(r"\(\s*(\S+)\s+(\S+)(?:\s+\S+)?\s*\)", seg[1])
                px = py = None
                for xs, ys in pts:
                    x = px if xs == "*" else int(xs)
                    y = py if ys == "*" else int(ys)
                    if px is not None:
                        length += abs(x - px) + abs(y - py)
                    px, py = x, y
            nets[name] = {"conns": [(c.replace("\\", ""), p) for c, p in conns], "len": length / unit}
    return {"unit": unit, "die": die, "rows": rows, "comps": comps, "pins": pins, "nets": nets}
