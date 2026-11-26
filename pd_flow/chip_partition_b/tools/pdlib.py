"""Architect B shared parsers: GF180 7-track Liberty/LEF, Yosys JSON netlists, DEF.
Pure python3 (host). Nothing here edits inputs."""
import json, os, re, hashlib
PDKV = "/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee"
SCL = f"{PDKV}/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0"
LIB_TT = f"{SCL}/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib"
LIB_SS = f"{SCL}/lib/gf180mcu_fd_sc_mcu7t5v0__ss_125C_3v00.lib"
LEF = f"{SCL}/lef/gf180mcu_fd_sc_mcu7t5v0.lef"
PFX = "gf180mcu_fd_sc_mcu7t5v0__"
SITE_W, ROW_H = 0.56, 3.92

def sha(p, n=16):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()[:n]

def _blocks(text, kw):
    for m in re.finditer(r"\b%s\s*\(\s*\"?([^\"\)]+)\"?\s*\)\s*\{" % kw, text):
        i = m.end(); depth = 1
        while depth:
            c = text[i]
            if c == "{": depth += 1
            elif c == "}": depth -= 1
            i += 1
        yield m.group(1).strip(), text[m.end():i - 1]

_LIB = {}
def liberty(path=LIB_TT):
    """{short cell name: {area, pins: {pin: {dir, cap, function}}, ff: bool}}"""
    if path in _LIB:
        return _LIB[path]
    text = open(path).read()
    out = {}
    for name, body in _blocks(text, "cell"):
        short = name.replace(PFX, "")
        a = re.search(r"\barea\s*:\s*([0-9.eE+-]+)", body)
        pins = {}
        for pn, pb in _blocks(body, "pin"):
            d = re.search(r"\bdirection\s*:\s*\"?(\w+)", pb)
            head = pb.split("{")[0]
            cap = re.search(r"\bcapacitance\s*:\s*([0-9.eE+-]+)", head)
            fn = re.search(r"\bfunction\s*:\s*\"([^\"]+)\"", pb)
            pins[pn] = {"dir": d.group(1) if d else None, "cap": float(cap.group(1)) if cap else 0.0,
                        "function": fn.group(1) if fn else None}
        out[short] = {"area": float(a.group(1)) if a else 0.0, "pins": pins,
                      "ff": bool(re.search(r"\bff\s*\(", body)), "latch": bool(re.search(r"\blatch\s*\(", body))}
    _LIB[path] = out
    return out

def lef_sizes(path=LEF):
    sizes, cur = {}, None
    for line in open(path):
        t = line.split()
        if not t: continue
        if t[0] == "MACRO": cur = t[1].replace(PFX, "")
        elif t[0] == "SIZE" and cur: sizes[cur] = (float(t[1]), float(t[3]))
        elif t[0] == "END" and len(t) > 1 and cur and t[1].replace(PFX, "") == cur: cur = None
    return sizes

def cell_class(short):
    """Coarse class (matches the metrics classes closely enough for synthesis netlists)."""
    if short.startswith(("dff", "sdff", "latq", "icg")): return "seq"
    if short.startswith(("tieh", "tiel")): return "tie"
    if short.startswith("clkinv"): return "clkinv"
    if short.startswith("clkbuf"): return "clkbuf"
    if short.startswith("inv"): return "inv"
    if short.startswith(("buf", "dly")): return "buf"
    if short.startswith("filltie"): return "tap"
    if short.startswith("endcap"): return "endcap"
    if short.startswith(("fill", "decap")): return "fill"
    if short.startswith("antenna"): return "antenna"
    return "logic"

def yosys_json(path):
    return json.load(open(path))

def module_cells(mod):
    """[(name, type_short, {pin: [bits]})] for library cells; submodule instances keep full type."""
    out = []
    for n, c in mod["cells"].items():
        t = c["type"]
        out.append((n, t.replace(PFX, "") if t.startswith(PFX) else t, c["connections"],
                    c.get("port_directions", {})))
    return out

def read_def(path):
    txt = open(path).read()
    dbu = int(re.search(r"UNITS DISTANCE MICRONS (\d+)", txt).group(1))
    die = [int(v) / dbu for v in re.search(r"DIEAREA \( (-?\d+) (-?\d+) \) \( (-?\d+) (-?\d+) \)", txt).groups()]
    rows = []
    for m in re.finditer(r"^ROW (\S+) (\S+) (\d+) (\d+) (\S+) DO (\d+) BY (\d+) STEP (\d+) (\d+)", txt, re.M):
        rows.append(dict(name=m.group(1), x=int(m.group(3)) / dbu, y=int(m.group(4)) / dbu,
                         orient=m.group(5), n=int(m.group(6)), step=int(m.group(8)) / dbu))
    comps = {}
    sec = re.search(r"^COMPONENTS \d+ ;(.*?)^END COMPONENTS", txt, re.S | re.M).group(1)
    for st in sec.split(";"):
        m = re.match(r"\s*-\s+(\S+)\s+(\S+)(.*)", st, re.S)
        if not m: continue
        name, master, rest = m.groups()
        p = re.search(r"\+\s+(PLACED|FIXED|FIRM|COVER)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+(\S+)", rest)
        comps[name.replace("\\", "")] = dict(master=master.replace(PFX, ""), status=p.group(1) if p else None,
                           x=int(p.group(2)) / dbu if p else None, y=int(p.group(3)) / dbu if p else None,
                           orient=p.group(4) if p else None)
    pins = {}
    m = re.search(r"^PINS \d+ ;(.*?)^END PINS", txt, re.S | re.M)
    if m:
        for st in m.group(1).split(";"):
            mm = re.match(r"\s*-\s+(\S+)\s+\+\s+NET\s+(\S+)(.*)", st, re.S)
            if not mm: continue
            pl = re.search(r"\+\s+(?:PLACED|FIXED)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)", mm.group(3))
            lay = re.search(r"LAYER\s+(\S+)", mm.group(3))
            if pl:
                pins[mm.group(1)] = dict(net=mm.group(2), x=int(pl.group(1)) / dbu, y=int(pl.group(2)) / dbu,
                                         layer=lay.group(1) if lay else None)
    return dict(dbu=dbu, die=die, rows=rows, comps=comps, pins=pins)
