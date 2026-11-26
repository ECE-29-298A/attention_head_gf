#!/usr/bin/env python3
"""Validator for the max_reg placements (experiments.md section 5 checklist), independent of the
generator's internal state wherever possible (it re-reads the emitted files).

  1 stale      gen_placement.py --check (regenerate in memory, diff against out/)
  2 views      netlist (Yosys flatten JSON), CSV, JSON, chip_anchor.cfg agree on instance, master,
               position and orientation; chip RTL `ifdef bodies equal the standalone netlists
  3 geometry   on the site/row grid; inside the footprint; no overlap; orientation legal for the row
               parity at both anchor parities; chip anchor inside rows 1..37 and clear of FIXED taps
               and endcaps (hard); M4 stripes reported (soft)
  4 intent     bit i in relative row i; compare chain hops exactly one row; aoi222 pin rule (chain on
               A1/B1) and oai21 gt on A1 (review finding B1); b_*: every instance in chip_anchor.cfg is a
               dffq_1 whose Q is the intended net in the names netlist
  5 connect    (a_*) one driver per net, every internal net has a sink, ports as golden
  6 function   (a_*) next state evaluated cell by cell from Liberty functions (flops from the Liberty
               ff next_state) on 2^18 random + directed vectors against the golden next state
               M' = en && (first || S_in > M) ? S_in : M (signed); ties may load (S_in == M)
  7 library    master widths in the LEF equal census.json; LEF sha256 logged
  8 pins       every signal pin has an on-grid access point at least 0.28 um inside the cell outline
  9 wells      DF.13_MV/DF.14_MV estimate: farthest cell point to the nearest well tie (tap/endcap) in
               the same row or the well-sharing neighbour row (Euclidean, 3.92 um vertical), <= 15 um
 10 self-test  deliberately illegal inputs; each must fire its INTENDED check
Usage: validate_placement.py [--out DIR] -> DIR/validation.json
"""
import argparse, copy, csv, io, json, math, os, random, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "tools"))
import gen_placement as G  # noqa: E402
from cellfun import liberty, compile_function, load_netlist  # noqa: E402

N = 22
VARS = ("a_sdff", "b_m", "b_ms")


def read_bundle(out, v):
    d = os.path.join(out, v)
    info = json.load(open(os.path.join(d, "placement.json")))
    rows = list(csv.DictReader(open(os.path.join(d, "placement.csv"))))
    cfg = [l.split() for l in open(os.path.join(d, "chip_anchor.cfg")) if l.strip()]
    return info, rows, cfg


# ----------------------------------------------------------------------------- checks
def check_geometry(v, info, rows, cfg, cen, ctx, E, notes):
    W, H = info["footprint"]["width_sites"], info["footprint"]["height_rows"]
    occ = {}
    for r in rows:
        rr, ss, ww = int(r["rel_row"]), int(r["rel_site"]), int(r["width_sites"])
        if ww != cen["masters"][G.P + r["master"]]["sites"]: E("geometry", f"{r['inst']} width {ww} != census")
        if abs(float(r["rel_x_um"]) - ss * G.SITE_W) > 1e-6 or abs(float(r["rel_y_um"]) - rr * G.ROW_H) > 1e-6:
            E("geometry", f"{r['inst']} off the site/row grid")
        if not (0 <= rr < H and 0 <= ss and ss + ww <= W): E("geometry", f"{r['inst']} outside footprint")
        for k in range(ss, ss + ww):
            if (rr, k) in occ: E("geometry", f"overlap row {rr} site {k}: {occ[(rr, k)]} / {r['inst']}")
            occ[(rr, k)] = r["inst"]
        for par, key in ((0, "orient_even_anchor"), (1, "orient_odd_anchor")):
            native = G.row_orient(rr + par)
            if r[key] not in (native, G.mirror(native)): E("geometry", f"{r['inst']} {key} {r[key]} illegal")
        # absolute
        ar, as_ = int(r["abs_row"]), int(r["abs_site"])
        if abs(float(r["abs_x_um"]) - (G.CORE_X0 + as_ * G.SITE_W)) > 1e-6 or abs(float(r["abs_y_um"]) - (G.CORE_Y0 + ar * G.ROW_H)) > 1e-6:
            E("geometry", f"{r['inst']} absolute off grid")
        if r["abs_orient"] not in (G.row_orient(ar), G.mirror(G.row_orient(ar))): E("geometry", f"{r['inst']} abs orient illegal")
        if not (1 <= ar <= G.CORE_ROWS - 2 and as_ >= 0 and as_ + ww <= G.CORE_SITES):
            E("outside_core", f"{r['inst']} outside rows 1..37 / core: row {ar} sites {as_}-{as_ + ww}")
            continue
        for t0, t1 in ctx["blocked"][ar]:
            if as_ < t1 and t0 < as_ + ww: E("tap", f"{r['inst']} overlaps FIXED tap/endcap row {ar} sites {t0}-{t1}")
    # abs overlap among cells
    aocc = {}
    for r in rows:
        for k in range(int(r["abs_site"]), int(r["abs_site"]) + int(r["width_sites"])):
            key = (int(r["abs_row"]), k)
            if key in aocc: E("geometry", f"abs overlap {key}")
            aocc[key] = r["inst"]
    if sum(int(r["width_sites"]) for r in rows) != info["bounds"]["site_rows_cells"]: E("geometry", "site-row checksum")
    # cfg agrees with CSV
    cmap = {r["chip_name"]: r for r in rows}
    if {l[0] for l in cfg} != set(cmap): E("views", "cfg names != CSV chip names")
    for name, x, y, o in cfg:
        r = cmap.get(name)
        if r and (abs(float(x) - float(r["abs_x_um"])) > 1e-6 or abs(float(y) - float(r["abs_y_um"])) > 1e-6 or o != r["abs_orient"]):
            E("views", f"cfg/CSV disagree {name}")
    # json cells agree with csv
    jc = {c["inst"]: c for c in info["cells"]}
    for r in rows:
        c = jc.get(r["inst"])
        if not c or c["master"] != r["master"] or c["rel_row"] != int(r["rel_row"]) or c["rel_site"] != int(r["rel_site"]):
            E("views", f"JSON/CSV disagree {r['inst']}")
    if v == "a_sdff" and not (int(rows[0]["abs_site"]) - int(rows[0]["rel_site"])) % 70 == 17: E("geometry", "a_sdff anchor rule")


def check_intent(v, info, rows, E, nl_names=None):
    jc = info["cells"]
    for c in jc:
        if c["bit"] is not None and c["rel_row"] != c["bit"]: E("intent", f"{c['inst']} bit {c['bit']} not in row {c['bit']}")
    if v.startswith("a_"):
        cmp = {c["bit"]: c for c in jc if c["role"] == "cmp"}
        if sorted(cmp) != list(range(1, N)): E("intent", "compare stages != 1..21")
        drv = {c["pins"]["ZN"]: c for c in cmp.values()}
        for i in range(2, N):
            z = cmp[i]["pins"]["A1"]
            if z != f"c[{i}]": E("intent", f"stage {i} chain input not on A1 ({z})")
            elif drv.get(z, {}).get("rel_row") != i - 1: E("intent", f"chain hop into stage {i} is not one row")
        if cmp[1]["pins"]["A1"] != "S_in[0]": E("intent", "stage 1 chain input must be S_in[0] on A1")
        for c in cmp.values():
            if c["master"] not in ("aoi21_1", "oai21_1"): E("intent", f"{c['inst']} chain cell {c['master']} not a 2-stack aoi21/oai21")
        slew_rule(jc, E)
        ld = [c for c in jc if c["inst"] == "u_ld"][0]
        if ld["pins"]["A1"] != "gt": E("intent", "oai21 gt not on A1 (fastest pin)")
    else:
        want = {"b_m": ["M"], "b_ms": ["M", "S"]}[v]
        roles = [c["role"] for c in jc]
        for r_ in want:
            if roles.count(r_) != N: E("intent", f"{r_} flop count {roles.count(r_)} != 22")
        qre = {"M": G.Q_M, "S": G.Q_S}
        for c in jc:
            t, pins = nl_names.get(c["inst"], (None, {}))
            m = re.fullmatch(qre[c["role"]], pins.get("Q", ""))
            if t != "dffq_1" or not m or int(m.group(1)) != c["bit"]:
                E("names", f"{c['inst']} is not the dffq_1 of {c['role']}[{c['bit']}] in the names netlist ({t}, {pins.get('Q')})")
        if v == "b_ms":
            for i in range(N):
                rs = [c for c in jc if c["bit"] == i]
                if len({c["rel_row"] for c in rs}) != 1: E("intent", f"bit {i} M and S not in one row")


_SLEW = {}


def slew_rule(cells, E, limit=2.7):
    """Every combinational master of the block must have Liberty ss_125C_3v00 rise and fall transition below
    0.9 x MAX_TRANSITION_CONSTRAINT (3 ns, DESIGN_REPAIR_MAX_SLEW_PCT 10) at input slew 1.226 ns and a
    13 fF load (table entry [3][3]); otherwise RepairDesignPostGPL resizes the FIXED cell in place and
    detailed placement fails on the overlap (measured: chip_runs/a_sdff_aoi222_FAILED)."""
    from cellfun import _blocks
    if not _SLEW:
        t = open(G_LIB().replace("tt_025C_3v30", "ss_125C_3v00")).read()
        for name, body, s0, e0 in _blocks(t, "cell"):
            if not name.startswith(G.P): continue
            vals = []
            for kind in ("rise_transition", "fall_transition"):
                for m in re.finditer(kind + r"\(\w+\) \{.*?values\((.*?)\);", body, re.S):
                    rows = [[float(x) for x in r.strip('"').split(",")] for r in re.findall(r'"[^"]*"', m.group(1))]
                    if len(rows) > 3 and len(rows[3]) > 3: vals.append(rows[3][3])
            _SLEW[name[len(G.P):]] = max(vals) if vals else 0.0
    for c in cells:
        if c["master"].startswith(("sdff", "dff")): continue
        if _SLEW.get(c["master"], 99) >= limit:
            E("slew", f"{c['inst']} {c['master']} ss transition {_SLEW.get(c['master'])} ns >= {limit} ns")


def ff_models(lib):
    txt = open(G_LIB()).read()
    out = {}
    for name, ins in (("dffq_1", ["D"]), ("sdffq_1", ["D", "SE", "SI"])):
        i = txt.find(f"cell({G.P}{name})"); j = txt.find("\n  cell(", i + 10)
        ns = re.search(r'next_state\s*:\s*"([^"]+)"', txt[i:j]).group(1)
        out[name] = compile_function(ns, ins)
    return out


def G_LIB():
    from cellfun import lib_path
    return lib_path()


def check_function(v, path, E, notes, nvec=1 << 18):
    nl = load_netlist(path, top="max_reg")
    masters = {i["master"] for i in nl["insts"].values()}
    lib = liberty(cells=masters)
    ffm = ff_models(lib)
    ports = nl["ports"]
    if sorted(ports) != ["M", "S_in", "clk", "en", "first"]: E("connect", f"ports {sorted(ports)}")
    if len(ports["S_in"]["bits"]) != N or len(ports["M"]["bits"]) != N: E("connect", "port widths")
    # connectivity
    drv, sinks = {}, {}
    for iname, inst in nl["insts"].items():
        for p, b in inst["conn"].items():
            d = lib[inst["master"]]["pins"][p]["dir"]
            if d == "output":
                if b in drv: E("connect", f"net {b} has two drivers")
                drv[b] = (iname, p)
            else:
                sinks.setdefault(b, []).append((iname, p))
    inb = {b for k in ("S_in", "clk", "en", "first") for b in ports[k]["bits"]}
    for b in drv:
        if b not in sinks and b not in ports["M"]["bits"]: E("connect", f"net {nl['names'].get(b, b)} has no sink")
    for b in sinks:
        if b not in drv and b not in inb and b not in ("0", "1"): E("connect", f"net {nl['names'].get(b, b)} undriven")
    for b in ports["M"]["bits"]:
        if drv.get(b, (None,))[0] is None or not nl["insts"][drv[b][0]]["master"].split("__")[-1].startswith(("dffq", "sdffq")):
            E("connect", "M bit not driven by a flop Q")
    # evaluation: comb cells topologically, flops cut (Q = state input, next = ff next_state)
    rnd = random.Random(20261126)
    vec = []
    for _ in range(nvec):
        s = rnd.getrandbits(22); m = rnd.getrandbits(22)
        if rnd.random() < 0.25: m = s ^ (1 << rnd.randrange(22))      # near-ties: hard compare cases
        if rnd.random() < 0.05: m = s                                   # exact ties
        vec.append((s, m, rnd.getrandbits(1), rnd.getrandbits(1)))
    for s in (0, (1 << 21), (1 << 21) - 1, (1 << 22) - 1):
        for m in (0, (1 << 21), (1 << 21) - 1, (1 << 22) - 1):
            for e in (0, 1):
                for f in (0, 1): vec.append((s, m, e, f))
    MASK = (1 << len(vec)) - 1
    val = {"0": 0, "1": MASK}
    def bitvec(sel, k):
        x = 0
        for j, t in enumerate(vec):
            if (t[sel] >> k) & 1: x |= 1 << j
        return x
    for k, b in enumerate(ports["S_in"]["bits"]): val[b] = bitvec(0, k)
    for k, b in enumerate(ports["M"]["bits"]): val[b] = bitvec(1, k)
    val[ports["en"]["bits"][0]] = bitvec(2, 0); val[ports["first"]["bits"][0]] = bitvec(3, 0)
    val[ports["clk"]["bits"][0]] = 0
    fn = {}
    for m in masters:
        ins = [p for p, d in lib[m]["pins"].items() if d["dir"] == "input"]
        if m.split("__")[-1] in ffm: continue
        fn[m] = {p: compile_function(d["function"], ins) for p, d in lib[m]["pins"].items() if d["dir"] == "output"}
    pending = [i for i in nl["insts"] if not nl["insts"][i]["master"].split("__")[-1] in ffm]
    guard = 0
    while pending:
        guard += 1
        if guard > 10000: E("function", "combinational loop or unresolved net"); return
        nxt = []
        for i in pending:
            inst = nl["insts"][i]; m = inst["master"]
            ins = {p: b for p, b in inst["conn"].items() if lib[m]["pins"][p]["dir"] == "input"}
            if all(b in val for b in ins.values()):
                pv = {p: val[b] for p, b in ins.items()}
                for p, f in fn[m].items(): val[inst["conn"][p]] = f(pv, MASK)
            else:
                nxt.append(i)
        pending = nxt
    nextM = [None] * N
    for i, inst in nl["insts"].items():
        mm = inst["master"].split("__")[-1]
        if mm in ffm:
            pv = {p: val[b] for p, b in inst["conn"].items() if p in ("D", "SE", "SI")}
            q = inst["conn"]["Q"]; k = ports["M"]["bits"].index(q)
            nextM[k] = ffm[mm](pv, MASK)
    bad = 0; ties_loaded = 0
    sgn = lambda x: x - (1 << 22) if x >> 21 else x
    for j, (s, m, e, f) in enumerate(vec):
        got = sum(((nextM[k] >> j) & 1) << k for k in range(N))
        want = s if (e and (f or sgn(s) > sgn(m))) else m
        if got != want and not (s == m and got == s):
            bad += 1
            if bad <= 3: E("function", f"vector s={s:06x} m={m:06x} en={e} first={f}: got {got:06x} want {want:06x}")
    notes.append(f"{v}: function {len(vec)} vectors, {bad} mismatches (golden next state, signed; ties may load)")
    if bad: E("function", f"{bad} mismatches")


def check_pins_lib(cen, E, notes):
    lef = open(G.LEF).read()
    for m, d in cen["masters"].items():
        w = float(re.search(rf"MACRO {m}\b.*?SIZE ([\d.]+) BY", lef, re.S).group(1))
        if abs(w - d["width_um"]) > 1e-9 or round(w / G.SITE_W) != d["sites"]: E("library", f"{m} LEF width {w} != census")
        for p, pd in d["pins"].items():
            if pd.get("dir") not in ("INPUT", "OUTPUT"): continue
            ok = [x for x in pd["access_x_N"] if 0.28 - 1e-9 <= x <= d["width_um"] - 0.28 + 1e-9]
            if not ok: E("pins", f"{m}.{p} has no access point >= 0.28 um inside the outline")
    notes.append(f"LEF sha256 {G.sha(G.LEF)}")


def well_check(rows, ctx, E, notes, v):
    """Per cell, per well, the farthest cell point to the nearest tie (tap or endcap, 2 sites) in the same row
    (dy 0) or the well-sharing neighbour row (dy 3.92). N row (even): N-well top, shared with row+1;
    FS row (odd): N-well bottom, shared with row-1. P-well is the other side."""
    worst = 0.0; where = None
    for r in rows:
        ar = int(r["abs_row"]); a = int(r["abs_site"]); b = a + int(r["width_sites"])
        nwell_nb = ar + 1 if ar % 2 == 0 else ar - 1
        pwell_nb = ar - 1 if ar % 2 == 0 else ar + 1
        for well, nb in (("N", nwell_nb), ("P", pwell_nb)):
            best_for_far = 0.0
            for s in range(a, b + 1):   # every site boundary of the cell
                dmin = 1e9
                for rr, dy in ((ar, 0.0), (nb, G.ROW_H)):
                    if not (0 <= rr < G.CORE_ROWS): continue
                    for t0, t1 in ctx["blocked"][rr]:
                        dx = 0.0 if t0 <= s <= t1 else min(abs(s - t0), abs(s - t1)) * G.SITE_W
                        dmin = min(dmin, math.hypot(dx, dy))
                best_for_far = max(best_for_far, dmin)
            if best_for_far > worst: worst, where = best_for_far, (r["inst"], ar, well)
    notes.append(f"{v}: DF.13/14 estimate worst cell-to-tie distance {worst:.2f} um at {where} (limit 15 um)")
    if worst > 15.0: E("wells", f"well-tie distance {worst:.2f} > 15 um at {where}")
    return worst


def run_all(out, selftest=True):
    errors = []; notes = []
    E = lambda k, m: errors.append(f"[{k}] {m}")
    cen = G.census(); ctx = G.chip_context()
    # 1 stale
    p = subprocess.run([sys.executable, os.path.join(HERE, "gen_placement.py"), "--out", out, "--check"], capture_output=True, text=True)
    notes.append("stale check: " + p.stdout.strip())
    if p.returncode: E("stale", p.stdout.strip())
    man = json.load(open(os.path.join(out, "MANIFEST.json")))
    names_nl = os.path.normpath(os.path.join(HERE, man["inputs"]["names_netlist"][0]))
    nl_names = G.parse_netlist(names_nl)
    res = {}
    for v in VARS:
        info, rows, cfg = read_bundle(out, v)
        check_geometry(v, info, rows, cfg, cen, ctx, E, notes)
        check_intent(v, info, rows, E, nl_names)
        res[v] = {"well_worst_um": round(well_check(rows, ctx, E, notes, v), 2)}
        if v.startswith("a_"):
            path = os.path.join(out, f"max_reg_{v}.v")
            nl = load_netlist(path, top="max_reg")
            ni = {k.lstrip("\\"): x["master"].split("__")[-1] for k, x in nl["insts"].items()}
            ci = {r["inst"]: r["master"] for r in rows}
            if ni != ci: E("views", f"{v}: netlist vs CSV instances differ {sorted(set(ni.items()) ^ set(ci.items()))[:4]}")
            check_function(v, path, E, notes)
    # chip RTL bodies equal the standalone netlists
    chip = open(os.path.join(out, "max_reg_chip.v")).read()
    for v, d in (("a_sdff", "MAX_REG_CELLS"),):
        body = open(os.path.join(out, f"max_reg_{v}.v")).read()
        body = body[body.index("module max_reg"):]
        if body not in chip: E("views", f"chip RTL {d} body != {v} netlist")
    gold = open(G.GOLDEN).read()
    gm = re.search(r"module max_reg.*?endmodule", gold, re.S).group(0)
    if gm not in chip: E("views", "chip RTL golden branch != golden module")
    check_pins_lib(cen, E, notes)
    st = selftests(out, cen, ctx, nl_names) if selftest else None
    if st is not None:
        for name, ok, fired in st:
            if not ok: E("selftest", f"{name}: intended check did not fire ({fired})")
    return {"ok": not errors, "errors": errors, "notes": notes, "per_variant": res,
            "selftests": [{"case": n, "ok": ok, "fired": f} for n, ok, f in (st or [])]}


def selftests(out, cen, ctx, nl_names):
    """Mutate the emitted CSV/JSON in memory; the intended check category must report."""
    cases = []
    def run(v, mut_rows=None, mut_info=None, want=""):
        info, rows, cfg = read_bundle(out, v)
        info = copy.deepcopy(info); rows = copy.deepcopy(rows)
        if mut_rows: mut_rows(rows)
        if mut_info: mut_info(info)
        cfg = [[r["chip_name"], r["abs_x_um"], r["abs_y_um"], r["abs_orient"]] for r in rows]
        errs = []
        Ee = lambda k, m: errs.append(f"[{k}] {m}")
        check_geometry(v, info, rows, cfg, cen, ctx, Ee, [])
        check_intent(v, info, rows, Ee, nl_names)
        return any(e.startswith(f"[{want}]") for e in errs), sorted({e.split("]")[0] + "]" for e in errs})
    def overlap(rows):
        rows[1]["rel_site"] = rows[0]["rel_site"]; rows[1]["rel_row"] = rows[0]["rel_row"]
        rows[1]["rel_x_um"] = rows[0]["rel_x_um"]; rows[1]["rel_y_um"] = rows[0]["rel_y_um"]
    def offgrid(rows): rows[0]["rel_x_um"] = str(float(rows[0]["rel_x_um"]) + 0.1)
    def badorient(rows): rows[0]["orient_even_anchor"] = "FS" if rows[0]["orient_even_anchor"] in ("N", "FN") else "N"
    def shift_abs(ds, dr=0):
        def f(rows):
            for r in rows:
                r["abs_site"] = str(int(r["abs_site"]) + ds); r["abs_row"] = str(int(r["abs_row"]) + dr)
                r["abs_x_um"] = f"{G.CORE_X0 + int(r['abs_site']) * G.SITE_W:.3f}"
                r["abs_y_um"] = f"{G.CORE_Y0 + int(r['abs_row']) * G.ROW_H:.3f}"
                r["abs_orient"] = G.row_orient(int(r["abs_row"])) if r["abs_orient"] in ("N", "FS") else G.mirror(G.row_orient(int(r["abs_row"])))
        return f
    def chain_break(info):
        for c in info["cells"]:
            if c["inst"] == "b05_cmp": c["rel_row"] = 7
    def pin_rule(info):
        for c in info["cells"]:
            if c["inst"] == "b07_cmp": c["pins"]["A1"], c["pins"]["A2"] = c["pins"]["A2"], c["pins"]["A1"]
    def gt_pin(info):
        for c in info["cells"]:
            if c["inst"] == "u_ld": c["pins"]["A1"], c["pins"]["B"] = c["pins"]["B"], c["pins"]["A1"]
    def slow_cell(info):
        for c in info["cells"]:
            if c["inst"] == "b06_cmp": c["master"] = "aoi222_1"
    def wrong_name(info):
        info["cells"][3]["inst"], info["cells"][4]["inst"] = info["cells"][4]["inst"], info["cells"][3]["inst"]
    # b_m column shifted 4 sites west of its window hits a tap; shifted to rows 17..38 leaves rows 1..37
    cases.append(("overlap", *run("a_sdff", overlap, want="geometry")))
    cases.append(("off-grid", *run("a_sdff", offgrid, want="geometry")))
    cases.append(("orientation vs row parity", *run("a_sdff", badorient, want="geometry")))
    cases.append(("tap overlap (b_m shifted -4 sites)", *run("b_m", shift_abs(-4), want="tap")))
    cases.append(("outside rows 1..37 (b_m shifted +16 rows)", *run("b_m", shift_abs(0, 16), want="outside_core")))
    cases.append(("compare chain broken", *run("a_sdff", mut_info=chain_break, want="intent")))
    cases.append(("chain input moved off A1", *run("a_sdff", mut_info=pin_rule, want="intent")))
    cases.append(("oai21 gt moved off A1", *run("a_sdff", mut_info=gt_pin, want="intent")))
    cases.append(("slow chain cell (aoi222_1) substituted", *run("a_sdff", mut_info=slow_cell, want="slew")))
    cases.append(("b_m instance names swapped", *run("b_m", mut_info=wrong_name, want="names")))
    return cases


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=os.path.join(HERE, "out"))
    a = ap.parse_args()
    r = run_all(a.out)
    json.dump(r, open(os.path.join(a.out, "..", "validation.json"), "w"), indent=1)
    for n in r["notes"]: print("NOTE", n)
    for s in r["selftests"]: print("SELFTEST", "ok " if s["ok"] else "BAD", s["case"], s["fired"])
    for e in r["errors"]: print("ERROR", e)
    print("ALL_OK" if r["ok"] else "FAILED")
    sys.exit(0 if r["ok"] else 1)


if __name__ == "__main__":
    main()
