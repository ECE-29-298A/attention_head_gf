#!/usr/bin/env python3
"""Cell function / pin-capacitance models from the GF180 7-track Liberty, and a bit-parallel
evaluator for flat gate-level netlists read through Yosys JSON.

- liberty(corner): {cell: {"pins": {pin: {"dir", "cap_pF", "function"}}, "area"}}
- load_netlist(path): Yosys `read_verilog; hierarchy; flatten; write_json` of a netlist whose
  cells are Liberty cells (blackboxed). Returns instances with master and pin->net-bit maps.
- Evaluator: nets are Python ints holding one bit per vector (bit-parallel). Cells are
  evaluated in topological order; cyclic or unresolved nets raise.
"""
import json, os, re, subprocess, tempfile

PDKV = "/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee"
LIBD = f"{PDKV}/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib"
PFX = "gf180mcu_fd_sc_mcu7t5v0__"
YOSYS = "/opt/homebrew/bin/yosys" if os.path.exists("/opt/homebrew/bin/yosys") else "yosys"


def lib_path(corner="tt_025C_3v30"):
    return f"{LIBD}/{PFX}{corner}.lib"


def _blocks(text, kw):
    """Yield (name, body) of top-level-within-text `kw(name) { ... }` groups (brace matched)."""
    for m in re.finditer(r"\b%s\s*\(\s*\"?([^\"\)]+)\"?\s*\)\s*\{" % kw, text):
        i = m.end(); depth = 1
        while depth:
            c = text[i]
            if c == "{": depth += 1
            elif c == "}": depth -= 1
            i += 1
        yield m.group(1).strip(), text[m.end():i - 1], m.start(), i


_LIB_CACHE = {}


def liberty(corner="tt_025C_3v30", cells=None):
    key = (corner, tuple(sorted(cells)) if cells else None)
    if key in _LIB_CACHE:
        return _LIB_CACHE[key]
    text = open(lib_path(corner)).read()
    out = {}
    for name, body, s, e in _blocks(text, "cell"):
        if cells and name not in cells:
            continue
        area = re.search(r"\barea\s*:\s*([0-9.eE+-]+)", body)
        pins = {}
        # only direct child pin groups: strip nested timing/power groups by brace matching per pin
        for pn, pb, ps, pe in _blocks(body, "pin"):
            d = re.search(r"\bdirection\s*:\s*\"?(\w+)", pb)
            # attributes before the first nested group belong to the pin itself
            head = pb.split("{")[0]
            cap = re.search(r"\bcapacitance\s*:\s*([0-9.eE+-]+)", head)
            fn = re.search(r"\bfunction\s*:\s*\"([^\"]+)\"", pb)
            pins[pn] = {"dir": d.group(1) if d else None,
                        "cap_pF": float(cap.group(1)) if cap else 0.0,
                        "function": fn.group(1) if fn else None}
        out[name] = {"area": float(area.group(1)) if area else None, "pins": pins}
    _LIB_CACHE[key] = out
    return out


def compile_function(expr, inputs):
    """Liberty boolean expression -> Python lambda over ints with an all-ones mask M."""
    s = expr.replace("'", "~POSTFIX")
    toks = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|[()!&|^*+~]|POSTFIX|\S", expr)
    # recursive-descent: or := xor ('|'|'+' xor)* ; xor := and ('^' and)* ; and := unary (('&'|'*'|juxt) unary)*
    pos = [0]
    def peek():
        return toks[pos[0]] if pos[0] < len(toks) else None
    def take():
        t = toks[pos[0]]; pos[0] += 1; return t
    def unary():
        t = peek()
        if t == "!":
            take(); v = unary(); r = f"(M ^ {v})"
        elif t == "(":
            take(); v = p_or(); assert take() == ")"; r = f"({v})"
        elif t in ("0", "1"):
            take(); r = "M" if t == "1" else "0"
        else:
            name = take(); assert name in inputs, (name, expr); r = f"v[{name!r}]"
        while peek() == "'":
            take(); r = f"(M ^ {r})"
        return r
    def p_and():
        r = unary()
        while peek() in ("&", "*") or (peek() not in (None, ")", "|", "+", "^")):
            if peek() in ("&", "*"): take()
            r = f"({r} & {unary()})"
        return r
    def p_xor():
        r = p_and()
        while peek() == "^":
            take(); r = f"({r} ^ {p_and()})"
        return r
    def p_or():
        r = p_xor()
        while peek() in ("|", "+"):
            take(); r = f"({r} | {p_xor()})"
        return r
    code = p_or()
    assert pos[0] == len(toks), (expr, toks)
    return eval(f"lambda v, M: {code}")


def load_netlist(path, top="ripple_add"):
    """Flatten via Yosys (cells blackboxed from the Liberty) and return a netlist dict."""
    with tempfile.TemporaryDirectory() as td:
        js = os.path.join(td, "n.json")
        cmd = (f"read_liberty -lib {lib_path()}; read_verilog -sv \"{path}\"; "
               f"hierarchy -check -top {top}; flatten; write_json {js}")
        subprocess.run([YOSYS, "-q", "-p", cmd], check=True)
        d = json.load(open(js))
    mod = d["modules"][top]
    ports = {n: {"dir": p["direction"], "bits": p["bits"]} for n, p in mod["ports"].items()}
    names = {}
    for n, nn in mod["netnames"].items():
        for i, b in enumerate(nn["bits"]):
            if isinstance(b, int):
                names.setdefault(b, f"{n}[{i}]" if len(nn["bits"]) > 1 else n)
    insts = {}
    for iname, c in mod["cells"].items():
        insts[iname] = {"master": c["type"], "conn": {p: bits[0] for p, bits in c["connections"].items()},
                        "dirs": c.get("port_directions", {})}
    return {"ports": ports, "insts": insts, "names": names}


class Evaluator:
    def __init__(self, nl, lib=None):
        self.nl = nl
        masters = {i["master"] for i in nl["insts"].values()}
        self.lib = lib or liberty(cells=masters)
        missing = masters - set(self.lib)
        assert not missing, missing
        self.fn = {}
        for m in masters:
            ins = [p for p, d in self.lib[m]["pins"].items() if d["dir"] == "input"]
            self.fn[m] = {p: compile_function(d["function"], ins)
                          for p, d in self.lib[m]["pins"].items() if d["dir"] == "output" and d["function"]}
        # driver map and topological order
        drv = {}
        for iname, inst in nl["insts"].items():
            for p, b in inst["conn"].items():
                if self.lib[inst["master"]]["pins"][p]["dir"] == "output" and isinstance(b, int):
                    assert b not in drv, ("multiple drivers", b, iname, drv.get(b))
                    drv[b] = (iname, p)
        self.drv = drv
        inputs = {b for p in nl["ports"].values() if p["dir"] == "input" for b in p["bits"]}
        order, state = [], {}
        def visit(i):
            st = state.get(i)
            if st == 1: raise ValueError(f"combinational cycle at {i}")
            if st == 2: return
            state[i] = 1
            inst = nl["insts"][i]
            for p, b in inst["conn"].items():
                if self.lib[inst["master"]]["pins"][p]["dir"] == "input" and isinstance(b, int):
                    if b in drv: visit(drv[b][0])
                    elif b not in inputs: raise ValueError(f"unresolved net {nl['names'].get(b, b)} at {i}.{p}")
            state[i] = 2; order.append(i)
        for i in sorted(nl["insts"]):
            visit(i)
        self.order = order

    def run(self, values, M):
        """values: {bit: int} for primary inputs (constants '0'/'1' handled). Returns all nets."""
        v = dict(values)
        def get(b):
            if b == "0": return 0
            if b == "1": return M
            return v[b]
        for i in self.order:
            inst = self.nl["insts"][i]; m = inst["master"]
            pv = {p: get(b) for p, b in inst["conn"].items() if self.lib[m]["pins"][p]["dir"] == "input"}
            for p, f in self.fn[m].items():
                b = inst["conn"].get(p)
                if isinstance(b, int):
                    v[b] = f(pv, M)
        return v

    def run_unit_delay(self, old, new, M, max_steps=500):
        """Synchronous unit-delay model: every cell output updates one step after its inputs.
        old/new: settled-start input maps. Returns per-net toggle counts (ints, popcount)."""
        v = self.run(old, M)
        for b, x in new.items(): v[b] = x
        tog = {}
        for b in new:
            tog[b] = bin(old[b] ^ new[b]).count("1")
        def get(b, vv):
            if b == "0": return 0
            if b == "1": return M
            return vv[b]
        for step in range(max_steps):
            changed = False; nv = dict(v)
            for i in self.order:
                inst = self.nl["insts"][i]; m = inst["master"]
                pv = {p: get(b, v) for p, b in inst["conn"].items() if self.lib[m]["pins"][p]["dir"] == "input"}
                for p, f in self.fn[m].items():
                    b = inst["conn"].get(p)
                    if isinstance(b, int):
                        x = f(pv, M)
                        d = x ^ v[b]
                        if d:
                            changed = True; tog[b] = tog.get(b, 0) + bin(d).count("1")
                        nv[b] = x
            v = nv
            if not changed:
                return tog, v, step
        raise RuntimeError("did not settle")
