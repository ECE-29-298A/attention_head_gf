#!/usr/bin/env python3
"""max_reg tetris placement generator (Phase 3, Agent 4). Single source of truth for every view.

Variants (PLAN.md section 2):
  a_sdff  fixed bit-sliced block: per bit row  sdffq_1 (flop + load mux in one cell) + compare slice
          (inv_1, nand2_1, nor2_1, aoi21_1/oai21_1 chain cell); one decode row (inv_1, oai21_1, buf_4).
          Gate-level netlist, all cells FIXED. (A dffq_1 + mux2_2 row does not fit one tap period with a
          slew-legal compare slice; mux2_1 is in the PDK's PnR exclusion list. See PLAN.md section 2.)
  b_m     placement-only: the 22 M flops of the shipped-flow netlist (ABC's in-context mapping kept)
          fixed in one 29-site column; everything else free.
  b_ms    placement-only: the 22 M flops and mac_unit's 22 S flops fixed as bit-aligned column pair.

Outputs (in --out, default out/):
  max_reg_a_sdff.v                     gate-level netlist (top max_reg, golden ports)
  max_reg_chip.v                       chip RTL: `ifdef MAX_REG_CELLS -> a_sdff netlist body, else the
                                       golden module (byte copy)
  <v>/placement.csv|json|svg           relative sub-placement (rel_row, rel_site, orientation per anchor
                                       parity, port sides, footprint, anchor rule, HPWL proxy)
  <v>/chip_anchor.cfg                  MACRO_PLACEMENT_CFG lines (name x y orient) at the chosen anchor
  <v>/names.json                       (b_*) Q net -> instance mapping, netlist path + sha256
  a_*/block.cfg, block_pins.cfg, block_librelane.json   Phase 4 standalone block inputs (untested)
  MANIFEST.json                        inputs and outputs with sha256
Usage: gen_placement.py [--out DIR] [--check] [--names-netlist NL] [--anchor V=ROW,SITE ...]
  --check  regenerate in memory and exit 1 if any file in DIR differs (stale check).
"""
import argparse, hashlib, io, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "tools"))
from defparse import read_def  # noqa: E402

P = "gf180mcu_fd_sc_mcu7t5v0__"
ROOT = os.path.normpath(os.path.join(HERE, "../../../.."))
BASE = os.path.join(ROOT, "pd_flow/baseline/harden")
BASE_DEF = os.path.join(BASE, "def/tt_um_attention_head_gf.def")
BASE_PNL = os.path.join(BASE, "pnl/tt_um_attention_head_gf.pnl.v")
BASE_NL = os.path.join(BASE, "nl/tt_um_attention_head_gf.nl.v")
GOLDEN = os.path.join(ROOT, "pd_flow/baseline/original_rtl/max_reg.v")
CENSUS = os.path.join(HERE, "census.json")
LEF = ("/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/"
       "libs.ref/gf180mcu_fd_sc_mcu7t5v0/lef/gf180mcu_fd_sc_mcu7t5v0.lef")
SITE_W, ROW_H = 0.56, 3.92
CORE_X0, CORE_Y0, CORE_SITES, CORE_ROWS = 3.36, 3.92, 607, 39
TAP_PERIOD = 70                 # sites; odd rows tap at 0 mod 70, even rows at 35 mod 70 (asserted)
INST_PATH = "core.max_unit"     # attention_controller instance of max_reg
N = 22


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def row_orient(abs_row):
    return "N" if abs_row % 2 == 0 else "FS"


def mirror(o):
    return {"N": "FN", "FS": "S", "FN": "N", "S": "FS"}[o]


def orient_x(x, w, o):
    return w - x if o in ("FN", "S") else x


# ----------------------------------------------------------------------------- library
def census():
    c = json.load(open(CENSUS))
    return c


def wsites(cen, m):
    return cen["masters"][P + m]["sites"]


def pin_x(cen, m, pin, o):
    """Mean on-grid Via1 access x of `pin` (cell-local um) after orientation."""
    xs = cen["masters"][P + m]["pins"][pin]["access_x_N"]
    w = cen["masters"][P + m]["width_um"]
    return sum(orient_x(x, w, o) for x in xs) / len(xs)


# ----------------------------------------------------------------------------- chip context
def chip_context():
    comps, _, dbu = read_def(BASE_DEF)
    txt = open(BASE_DEF).read()
    rows = re.findall(r"^ROW ROW_(\d+) (\S+) (\d+) (\d+) (\S+) DO (\d+) BY 1 STEP (\d+) 0 ;", txt, re.M)
    assert len(rows) == CORE_ROWS
    for r, site, x, y, o, cnt, step in rows:
        assert site == "GF018hv5v_mcu_sc7" and int(x) / dbu == CORE_X0 and int(cnt) == CORE_SITES
        assert abs(int(y) / dbu - (CORE_Y0 + int(r) * ROW_H)) < 1e-9 and o == row_orient(int(r))
    blocked = {r: [] for r in range(CORE_ROWS)}
    for name, c in comps.items():
        if c["status"] == "FIXED" and ("filltie" in c["master"] or "endcap" in c["master"]):
            r = int(round((c["y"] - CORE_Y0) / ROW_H)); s0 = int(round((c["x"] - CORE_X0) / SITE_W))
            blocked[r].append((s0, s0 + 2))
    # assert the tap rule the templates rely on (rows 1..37: endcaps at 0 and 605, taps every 70)
    for r in range(1, CORE_ROWS - 1):
        taps = sorted(s for s, _ in blocked[r] if s not in (0, 605))
        ph = 0 if r % 2 else 35
        assert taps and all(s % TAP_PERIOD == ph for s in taps), (r, taps)
    stripes = []
    sec = txt[txt.index("SPECIALNETS"):txt.index("END SPECIALNETS")]
    cur = None
    for line in sec.splitlines():
        m = re.match(r"\s*- (\S+)", line)
        if m: cur = m.group(1)
        for w, x in re.findall(r"Metal4 (\d+) \+ SHAPE STRIPE \( (\d+) \d+ \)", line):
            stripes.append({"net": cur, "x_center": int(x) / dbu, "width": int(w) / dbu})
    return {"blocked": blocked, "m4_stripes": sorted(stripes, key=lambda s: s["x_center"]),
            "def": os.path.relpath(BASE_DEF, HERE), "def_sha256": sha(BASE_DEF)}


# ----------------------------------------------------------------------------- shipped netlist
def parse_netlist(fn):
    cells = {}
    for m in re.finditer(r'gf180mcu_fd_sc_mcu7t5v0__(\w+)\s+(\S+)\s*\((.*?)\);', open(fn).read(), re.S):
        t, n, body = m.groups()
        pins = {p: net.strip().lstrip("\\").strip() for p, net in re.findall(r'\.(\w+)\s*\(\s*([^()]*?)\s*\)', body)}
        cells[n] = (t, pins)
    return cells


def flop_map(cells, qre):
    out = {}
    for n, (t, p) in cells.items():
        m = re.fullmatch(qre, p.get("Q", ""))
        if t.startswith(("dff", "sdff")) and m:
            out[int(m.group(1))] = {"inst": n, "master": t, "q": p["Q"], "d": p.get("D")}
    return out


Q_M = r"core\.mac\.M\[(\d+)\]"
Q_S = r"core\.exponent_unit\.D\[(\d+)\]"     # mac_unit's S register (net named after exp_lut's D)


# ----------------------------------------------------------------------------- variants
def cell(inst, master, role, bit, row, site, pins, mir=False):
    return {"inst": inst, "master": master, "role": role, "bit": bit, "rel_row": row, "rel_site": site,
            "mirror": mir, "pins": pins}


def build_block(v="a_sdff"):
    """Bit-sliced block. Row i = bit i: sdffq_1 (flop + load mux: Q+ = SE ? SI : D with D = S_in[i], SI = M[i],
    SE = nld) plus compare stage i (i >= 1); row 22 = decode. Chain c[i] (i = 2..22) is stage i-1's output.
    Stage i computes g_{i+1} = maj(s, ~m, g_i), g = (S_in[i:0] > M[i:0]) unsigned, as p + t*g with
    p = s & ~m, t = s | ~m, in alternating polarity so that every chain cell is a single 2-stack gate:
      odd  i (1..19): z = c[i] = g_i (true)  -> c[i+1] = ~g_{i+1} = aoi21(A1 = z, A2 = t, B = p);
                      sb = inv(S_in[i]), t = nand2(sb, M[i]), p = nor2(sb, M[i])
      even i (2..20): z = c[i] = ~g_i        -> c[i+1] =  g_{i+1} = oai21(A1 = z, A2 = ~t, B = ~p);
                      mb = inv(M[i]), ~t = nor2(S_in[i], mb), ~p = nand2(S_in[i], mb)
      i = 21 (sign, offset binary s' = ~s, m' = ~m): z = c[21] true -> c[22] = ~gt = aoi21(z, t', p') with
                      t' = ~s | m = nand2(S_in[21], mb), p' = ~s & m = nor2(S_in[21], mb), mb = inv(M[21])
    Stage 1 takes z = S_in[0] (tie don't-care, Phase 2 c10: loading S_in == M keeps M).
    Decode: gt = inv(c[22]); nld = oai21(A1 = gt, A2 = first, B = en) = ~(en & (first | gt)); nld_b = buf_4.
    Cell choice: aoi222_1 (one-cell majority) was tried first and rejected: its ss rise transition (about
    3.5 ns at 1.2 ns input, 6-13 fF) exceeds MAX_TRANSITION_CONSTRAINT 3 ns, so RepairDesignPostGPL upsized
    20 FIXED aoi222 in place and detailed placement failed on overlaps (chip_runs/a_sdff_aoi222_FAILED).
    aoi21_1 / oai21_1 / nand2_1 / nor2_1 stay below 1.8 ns there (evidence/arcs_ss_summary.txt).
    Pin rule (review B1): the late, glitching chain input z takes A1, the faster of the A pair
    (aoi21_1 rise 0.698 vs 0.803 ns, oai21_1 0.740 vs 0.792 ns at ss [2][2]); gt takes oai21 A1.
    Row templates (anchor site = 17 mod 70, anchor row even; chip taps then sit at rel site 18-19 in even
    rows and 53-54 in odd rows):
      even row: inv 0 | nand2 4 | nor2 9 | (tap 18) | chain oai21 20 | sdffq 28
      odd  row: chain aoi21 7 | sdffq 15 | (tap 53) | inv 55 | nand2 59 | nor2 64
      decode  : inv 0 | oai21 4 | (tap 18) | buf_4 20"""
    cells = []
    for i in range(N):
        even = i % 2 == 0
        cells.append(cell("b%02d_ff" % i, "sdffq_1", "ff", i, i, 28 if even else 15,
                          {"D": "S_in[%d]" % i, "SI": "M[%d]" % i, "SE": "nld_b", "CLK": "clk", "Q": "M[%d]" % i}))
        if i == 0:
            continue
        z = "S_in[0]" if i == 1 else "c[%d]" % i
        s, m = "S_in[%d]" % i, "M[%d]" % i
        if i % 2 == 1 and i != 21:      # invert S_in, aoi21 chain
            inv = (s, "xi[%d]" % i); g1 = ("xi[%d]" % i, m); chain = "aoi21_1"
        else:                            # invert M, oai21 chain (even) / aoi21 (bit 21)
            inv = (m, "xi[%d]" % i); g1 = (s, "xi[%d]" % i); chain = "aoi21_1" if i == 21 else "oai21_1"
        sites = {"inv": 0, "nand": 4, "nor": 9, "chain": 20} if even else {"inv": 55, "nand": 59, "nor": 64, "chain": 7}
        cells.append(cell("b%02d_inv" % i, "inv_1", "inv", i, i, sites["inv"], {"I": inv[0], "ZN": inv[1]}))
        cells.append(cell("b%02d_nand" % i, "nand2_1", "pg", i, i, sites["nand"],
                          {"A1": g1[0], "A2": g1[1], "ZN": "na[%d]" % i}))
        cells.append(cell("b%02d_nor" % i, "nor2_1", "pg", i, i, sites["nor"],
                          {"A1": g1[0], "A2": g1[1], "ZN": "no[%d]" % i}))
        if chain == "aoi21_1":           # odd / 21: nand -> t, nor -> p (true polarity)
            cp = {"A1": z, "A2": "na[%d]" % i, "B": "no[%d]" % i, "ZN": "c[%d]" % (i + 1)}
        else:                            # even: nor -> ~t, nand -> ~p
            cp = {"A1": z, "A2": "no[%d]" % i, "B": "na[%d]" % i, "ZN": "c[%d]" % (i + 1)}
        cells.append(cell("b%02d_cmp" % i, chain, "cmp", i, i, sites["chain"], cp))
    dr = N
    cells.append(cell("u_gt_inv", "inv_1", "dec", None, dr, 0, {"I": "c[22]", "ZN": "gt"}))
    cells.append(cell("u_ld", "oai21_1", "dec", None, dr, 4, {"A1": "gt", "A2": "first", "B": "en", "ZN": "nld"}))
    cells.append(cell("u_ld_buf", "buf_4", "dec", None, dr, 20, {"I": "nld", "Z": "nld_b"}))
    return cells


def build_flops(v, nlcells):
    """b_m: M flops at rel site 0. b_ms: S flop at rel site 0 (west window), M flop at rel site 35
    (east window): one bit per row, tap column between."""
    M = flop_map(nlcells, Q_M); S = flop_map(nlcells, Q_S)
    assert sorted(M) == list(range(N)) and sorted(S) == list(range(N)), (sorted(M), sorted(S))
    cells = []
    for i in range(N):
        assert M[i]["master"] == "dffq_1" and S[i]["master"] == "dffq_1"
        if v == "b_m":
            cells.append(cell(M[i]["inst"], "dffq_1", "M", i, i, 0, {"D": M[i]["d"], "CLK": "clk", "Q": M[i]["q"]}))
        else:
            cells.append(cell(S[i]["inst"], "dffq_1", "S", i, i, 0, {"D": S[i]["d"], "CLK": "clk", "Q": S[i]["q"]}))
            cells.append(cell(M[i]["inst"], "dffq_1", "M", i, i, 35, {"D": M[i]["d"], "CLK": "clk", "Q": M[i]["q"]}))
    return cells, M, S


def footprint(cells, cen, v):
    w = max(c["rel_site"] + wsites(cen, c["master"]) for c in cells)
    w = {"a_sdff": 70}.get(v, w)
    return w, max(c["rel_row"] for c in cells) + 1


# anchor rules (hard, beyond "inside core and clear of FIXED taps/endcaps", which is checked per anchor)
ANCHOR_RULE = {
    "a_sdff": "site = 17 (mod 70) and row even: the tap falls at rel site 18-19 in even rows and 53-54 in odd "
              "rows, the gaps the two row templates leave",
    "b_m": "any site where the 29-site flop column clears every tap (inside a 33-site window)",
    "b_ms": "site = 2 (mod 35): the S column (29 sites) and the M column (rel site 35) each sit in a 33-site "
            "tap window; the tap column at rel site 33-34 (alternate rows) falls between them",
}


def anchor_ok_rule(v, r0, s0):
    if v == "a_sdff": return s0 % 70 == 17 and r0 % 2 == 0
    if v == "b_ms": return s0 % 35 == 2
    return True


def place(cells, cen, anchor, order_up=True, mir=False):
    """Absolute placement: list of (cell, abs_row, abs_site, orient, x_um, y_um)."""
    r0, s0 = anchor
    H = max(c["rel_row"] for c in cells) + 1
    out = []
    for c in cells:
        rr = c["rel_row"] if order_up else (H - 1 - c["rel_row"])
        r = r0 + rr; s = s0 + c["rel_site"]
        o = row_orient(r)
        if c["mirror"] ^ mir: o = mirror(o)
        out.append((c, r, s, o, round(CORE_X0 + s * SITE_W, 3), round(CORE_Y0 + r * ROW_H, 3)))
    return out


def anchor_check(cells, cen, ctx, anchor, order_up=True):
    hard, soft = [], []
    for c, r, s, o, x, y in place(cells, cen, anchor, order_up):
        w = wsites(cen, c["master"])
        if not (1 <= r < CORE_ROWS - 1 and 0 <= s and s + w <= CORE_SITES):
            hard.append(f"{c['inst']} outside rows 1..37 / core (row {r}, sites {s}-{s + w})"); continue
        for t0, t1 in ctx["blocked"][r]:
            if s < t1 and t0 < s + w:
                hard.append(f"{c['inst']} overlaps FIXED tap/endcap row {r} sites {t0}-{t1}")
        x1 = x + w * SITE_W
        for st in ctx["m4_stripes"]:
            if x < st["x_center"] + st["width"] / 2 + 0.28 and st["x_center"] - st["width"] / 2 - 0.28 < x1:
                soft.append(f"{c['inst']} under M4 {st['net']} x={st['x_center']}")
    return hard, soft


def legal_anchors(cells, cen, ctx, v):
    W, H = footprint(cells, cen, v)
    out = []
    for r0 in range(1, CORE_ROWS - H):
        for s0 in range(0, CORE_SITES - W + 1):
            if not anchor_ok_rule(v, r0, s0): continue
            hard, soft = anchor_check(cells, cen, ctx, (r0, s0))
            if not hard:
                out.append((r0, s0, len(soft)))
    return out


# ----------------------------------------------------------------------------- neighbour proxy
def neighbour_model(cen):
    """Baseline (free-placed) neighbours of max_reg, from the shipped baseline DEF + pnl.
    Returns per-net endpoint positions of cells that are NOT part of the variant (estimate: the global
    placer will move them; used only to rank anchors)."""
    comps, _, _ = read_def(BASE_DEF)
    cells = parse_netlist(BASE_PNL)
    lefw = {m: float(w) for m, w in re.findall(r"MACRO (\S+).*?SIZE ([\d.]+) BY", open(LEF).read(), re.S)}
    def ctr(n):
        c = comps.get(n) or comps.get(re.sub(r"([\[\]])", r"\\\1", n))
        return (c["x"] + lefw[c["master"]] / 2, c["y"] + ROW_H / 2) if c else None
    drv, loads = {}, {}
    for n, (t, pins) in cells.items():
        for p, net in pins.items():
            if p in ("Z", "ZN", "Q"): drv[net] = n
            else: loads.setdefault(net, []).append(n)
    M = flop_map(cells, Q_M); S = flop_map(cells, Q_S)
    # max_reg exclusive cone (cone.py definition)
    mset = {M[k]["inst"] for k in M}
    cone = set(); stack = [M[k]["d"] for k in M]
    while stack:
        net = stack.pop(); c = drv.get(net)
        if c is None or c in cone: continue
        t, pins = cells[c]
        if t.startswith(("dff", "sdff", "tie")): continue
        cone.add(c); stack += [v for p, v in pins.items() if p not in ("Z", "ZN", "Q")]
    excl = set(cone); ch = True
    while ch:
        ch = False
        for c in list(excl):
            outs = [v for p, v in cells[c][1].items() if p in ("Z", "ZN", "Q")]
            if any(l not in excl and l not in mset for o in outs for l in loads.get(o, [])):
                excl.discard(c); ch = True
    return {"comps": comps, "cells": cells, "drv": drv, "loads": loads, "M": M, "S": S, "excl": excl,
            "ctr": ctr}


def proxy(v, cells, cen, anchor, nb, order_up=True, mir=False):
    """HPWL proxy (um) of the nets that cross the variant's boundary, fixed pins at their access-point x
    (row centre y), free neighbours at baseline cell centres. Block internal nets are listed separately."""
    pl = place(cells, cen, anchor, order_up, mir)
    pos = {}
    for c, r, s, o, x, y in pl:
        for pin, net in c["pins"].items():
            pos.setdefault(net, []).append((x + pin_x(cen, c["master"], pin, o), y + ROW_H / 2))
    ext = {}
    M, S, excl, drv, loads, ctr = nb["M"], nb["S"], nb["excl"], nb["drv"], nb["loads"], nb["ctr"]
    if v.startswith("a_"):
        mset = {M[k]["inst"] for k in M}
        for k in range(N):
            qs = S[k]["q"]                  # S_in[k]: S flop + its loads outside max_reg
            pts = [ctr(S[k]["inst"])] + [ctr(l) for l in loads.get(qs, []) if l not in excl and l not in mset]
            ext["S_in[%d]" % k] = [p for p in pts if p] + pos.get("S_in[%d]" % k, [])
            qm = M[k]["q"]                  # M[k]: loads outside max_reg (mac_unit's S load mux)
            pts = [ctr(l) for l in loads.get(qm, []) if l not in excl and l not in mset]
            ext["M[%d]" % k] = [p for p in pts if p] + pos.get("M[%d]" % k, [])
    else:
        fixed = {c["inst"] for c in cells}
        nets = set()
        for c in cells:
            nets |= {c["pins"]["Q"], c["pins"]["D"]}
        for net in nets:
            pts = []
            ends = ([drv[net]] if net in drv else []) + loads.get(net, [])
            for e in ends:
                if e not in fixed:
                    p = ctr(e)
                    if p: pts.append(p)
            ext[net] = pts + pos.get(net, [])
    hp = lambda ps: (max(p[0] for p in ps) - min(p[0] for p in ps) + max(p[1] for p in ps) - min(p[1] for p in ps)) if len(ps) > 1 else 0.0
    ext_um = sum(hp(ps) for ps in ext.values())
    internal = 0.0
    if v.startswith("a_"):
        for net, ps in pos.items():
            if net in ext or net == "clk": continue
            internal += hp(ps)
    return round(ext_um, 2), round(internal, 2)


def choose(v, cells, cen, ctx, nb, forced=None):
    la = legal_anchors(cells, cen, ctx, v)
    cands = []
    orders = (True,) if v.startswith("a_") else (True, False)
    mirs = (False,) if v.startswith("a_") else (False, True)
    for r0, s0, nsoft in la:
        if forced and (r0, s0) != forced: continue
        for ou in orders:
            for mi in mirs:
                e, i = proxy(v, cells, cen, (r0, s0), nb, ou, mi)
                cands.append({"row": r0, "site": s0, "order_up": ou, "mirror": mi, "ext_hpwl_um": e,
                              "internal_hpwl_um": i, "m4_soft_hits": nsoft})
    assert cands, f"no legal anchor for {v} (forced={forced})"
    cands.sort(key=lambda d: (d["ext_hpwl_um"] + d["internal_hpwl_um"], d["row"], d["site"], not d["order_up"], d["mirror"]))
    return cands[0], cands, la


# ----------------------------------------------------------------------------- views
HDR = "// Generated by pd_flow/modules/max_reg/layout_plan/gen_placement.py. Do not edit.\n"


def netlist_body(cells):
    lines = ["    wire [22:2] c;      // compare chain, polarity alternates per stage (gen_placement.build_block)",
             "    wire [21:1] xi;     // per-stage inverter output (~S_in[i] or ~M[i])",
             "    wire [21:1] na, no; // per-stage nand2 / nor2 outputs (t, p or their complements)",
             "    wire gt, nld, nld_b;"]
    for c in cells:
        conn = ", ".join(f".{p}({n})" for p, n in c["pins"].items())
        lines.append(f"    {P}{c['master']} {c['inst']} ({conn});")
    return "\n".join(lines) + "\n"


PORTS = ("    input  wire              clk,\n    input  wire              first,\n    input  wire              en,\n"
         "    input  wire signed [21:0] S_in,\n    output wire signed [21:0] M\n")


def netlist_text(v, cells):
    return (HDR + f"// max_reg variant {v}: gate-level netlist, GF180 7-track cells, instance names = placement names.\n"
            "// Function: M <= (en && (first || S_in > M)) ? S_in : M (golden), with a tie don't-care.\n"
            f"module max_reg (\n{PORTS});\n" + netlist_body(cells) + "endmodule\n")


def chip_rtl_text(cs):
    gold = open(GOLDEN).read()
    m = re.search(r"module max_reg.*?endmodule", gold, re.S)
    head = gold[:m.start()]
    return (head + "// Chip RTL with an optional cell-built body (pd_flow/modules/max_reg/layout_plan, Phase 3).\n"
            "// `MAX_REG_CELLS` (set only through LibreLane VERILOG_DEFINES): variant a_sdff. Without it every tool\n"
            "// sees the golden module below, unchanged.\n"
            "`ifdef MAX_REG_CELLS\n" + f"module max_reg (\n{PORTS});\n" + netlist_body(cs) + "endmodule\n"
            "`else\n" + gold[m.start():m.end()] + "\n`endif\n" + gold[m.end():].lstrip("\n"))


def flopcells_text():
    """Stable-name alternative for the placement-only variants: the 22 M flops as explicit dffq_1 instances
    (core.max_unit.bNN_ff in the chip, independent of Yosys numbering) and the golden next-state logic left
    behavioural, so ABC still maps compare + load mux in context. Not adopted (PLAN.md section 3.3)."""
    ff = "\n".join(f"    {P}dffq_1 b{i:02d}_ff (.D(d[{i}]), .CLK(clk), .Q(M[{i}]));" for i in range(N))
    return (HDR + "// max_reg variant b_flopcells: explicit flop cells (stable instance names), behavioural next state.\n"
            f"module max_reg (\n{PORTS});\n"
            "    wire [21:0] d = (en && (first || S_in > M)) ? S_in : M;\n" + ff + "\nendmodule\n")


def chip_name(v, c):
    return f"{INST_PATH}.{c['inst']}" if v.startswith("a_") else c["inst"]


def csv_text(v, cells, cen, best):
    out = io.StringIO()
    out.write("inst,chip_name,master,role,bit,rel_row,rel_site,width_sites,rel_x_um,rel_y_um,orient_even_anchor,orient_odd_anchor,abs_row,abs_site,abs_x_um,abs_y_um,abs_orient\n")
    pl = place(cells, cen, (best["row"], best["site"]), best["order_up"], best["mirror"])
    for (c, r, s, o, x, y) in pl:
        oe = row_orient(c["rel_row"]); oo = row_orient(c["rel_row"] + 1)
        if c["mirror"] ^ best["mirror"]: oe, oo = mirror(oe), mirror(oo)
        out.write(f"{c['inst']},{chip_name(v, c)},{c['master']},{c['role']},{'' if c['bit'] is None else c['bit']},"
                  f"{c['rel_row']},{c['rel_site']},{wsites(cen, c['master'])},{c['rel_site'] * SITE_W:.2f},"
                  f"{c['rel_row'] * ROW_H:.2f},{oe},{oo},{r},{s},{x:.3f},{y:.3f},{o}\n")
    return out.getvalue()


def cfg_text(v, cells, cen, best):
    pl = place(cells, cen, (best["row"], best["site"]), best["order_up"], best["mirror"])
    return "".join(f"{chip_name(v, c)} {x:.2f} {y:.2f} {o}\n" for c, r, s, o, x, y in pl)


def ports(v, cells, cen):
    if v.startswith("a_"):
        return {"west": "S_in[i] and M[i] in relative row i (S_in from mac_unit's S flop, M to mac_unit's S load mux; "
                        "both on the mac side)",
                "north": "first, en into the decode row (row 22); controller decode lives above",
                "clock": "clk to every flop CLK (sdffq_1 CLK at x 5.88-6.44 um in the cell; dffq_1 CLK at 0.84-1.4)",
                "south": "none (the chain starts at bit 0 inside: c[1] = S_in[0])",
                "east": "none"}
    if v == "b_m":
        return {"west_or_east": "Q (M[i]) faces the side picked by the mirror search; D from ABC's free mux/compare",
                "pin_order": "bit i in relative row i (order_up) or row 21-i"}
    return {"west": "S flop column (mac_unit S register), Q -> adder a input / exp_lut / compare, D <- mac sum / load mux",
            "east": "M flop column (max_reg), Q -> compare and mac S load mux, D <- ABC's load mux",
            "pin_order": "bit i in relative row i: M[i] beside S[i] in the same row"}


def svg_text(v, cells, cen, best):
    W, H = footprint(cells, cen, v)
    sc = 6; pad = 10
    col = {"ff": "#7aa6d8", "M": "#7aa6d8", "S": "#9fd39a", "cmp": "#e8b04a", "inv": "#d98c8c", "mux": "#b39ddb",
           "dec": "#888888"}
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W * SITE_W * sc + 2 * pad:.0f}" height="{H * ROW_H * sc + 2 * pad:.0f}">',
         f'<rect x="{pad}" y="{pad}" width="{W * SITE_W * sc:.1f}" height="{H * ROW_H * sc:.1f}" fill="none" stroke="black"/>']
    for c in cells:
        x = pad + c["rel_site"] * SITE_W * sc; y = pad + (H - 1 - c["rel_row"]) * ROW_H * sc
        w = wsites(cen, c["master"]) * SITE_W * sc
        o.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{ROW_H * sc:.1f}" fill="{col.get(c["role"], "#ccc")}" stroke="black" stroke-width="0.5"/>')
        o.append(f'<text x="{x + 2:.1f}" y="{y + 13:.1f}" font-size="9">{c["inst"] if v.startswith("a_") else c["role"] + str(c["bit"])} {c["master"]}</text>')
    o.append("</svg>\n")
    return "\n".join(o)


def bounds(cells, cen, v):
    W, H = footprint(cells, cen, v)
    used = sum(wsites(cen, c["master"]) for c in cells)
    taps = H * 2 if v == "a_sdff" else (H // 2) * 2 if v == "b_ms" else 0
    widest = max(wsites(cen, c["master"]) for c in cells)
    per_row = {}
    for c in cells:
        per_row[c["rel_row"]] = per_row.get(c["rel_row"], 0) + wsites(cen, c["master"])
    return {"footprint_sites": W, "rows": H, "site_rows_box": W * H, "site_rows_cells": used,
            "site_rows_taps_inside_estimate": taps, "utilization_box": round(used / (W * H), 4),
            "area_box_um2": round(W * SITE_W * H * ROW_H, 2),
            "cell_area_um2": round(sum(cen["masters"][P + c["master"]]["area_um2"] for c in cells), 4),
            "widest_cell_sites": widest, "max_row_sites": max(per_row.values()),
            "area_floor_sites_at_rows": -(-used // H),
            "note": "bit rows cannot be narrower than the widest row template (flop + compare + inverter [+ mux]); "
                    "the free sites are ragged capacity for neighbours (D5), not a halo"}


BLK_WEST, BLK_EAST, BLK_ROW0 = 17, 3, 2   # block-core sites west / east of the footprint, rows below it


def block_files(v, cells, cen):
    """Phase 4 standalone block that reproduces the chip context of the footprint (estimate, to be asserted
    after TapEndcapInsertion in Phase 4):
      - core origin (3.36, 3.92) as in the chip, FP_TAPCELL_DIST 20 as in the chip: the tool should place
        taps at block sites 0 mod 70 in odd rows and 35 mod 70 in even rows, the chip phase;
      - footprint at block site 17 (= the chip anchor rule site 17 mod 70), so the taps land at rel site
        53 (odd rows) and 18 (even rows), the template gaps; 3 sites east for the east endcap;
      - footprint at block row 2 (even, as the anchor rule needs); rows 0 and top get the dense boundary taps
        (chip rows 0 and 38 do), row 1 and the row below the top row stay free."""
    W, H = footprint(cells, cen, v)
    core_sites = BLK_WEST + W + BLK_EAST
    rows = BLK_ROW0 + H + 2
    die_w = round(CORE_X0 * 2 + core_sites * SITE_W, 2); die_h = round(CORE_Y0 * 2 + rows * ROW_H, 2)
    lines = []
    for c in cells:
        r = BLK_ROW0 + c["rel_row"]; s = BLK_WEST + c["rel_site"]
        o = row_orient(r)
        if c["mirror"]: o = mirror(o)
        lines.append(f"{c['inst']} {CORE_X0 + s * SITE_W:.2f} {CORE_Y0 + r * ROW_H:.2f} {o}")
    pins = ["#N", "first", "en", "#W"]
    for i in range(N):
        pins += [f"S_in\\[{i}\\]", f"M\\[{i}\\]"]
    pins += ["#S", "clk"]
    lib = {
        "//": "UNTESTED Phase 4 starting point generated by gen_placement.py (see PLAN.md section 7).",
        "//deviation_pdn": "block die %.2f um wide vs the 38.87 um stripe pitch: the Metal4 VPWR/VGND pairs fall at "
                           "different x than at the chip anchor; rail via stacks may land over block cells" % die_w,
        "//deviation_io": "ports on the die edge (W: S_in/M interleaved bottom to top; N: first, en; S: clk) instead of "
                          "chip neighbours; boundary wire is not chip-representative",
        "//assert_after_tapendcap": "taps exactly at the chip phase (block sites 0 mod 70 odd rows, 35 mod 70 even "
                                    "rows); none overlapping a FIXED block cell; endcaps at both row ends",
        "DESIGN_NAME": "max_reg", "VERILOG_FILES": f"dir::max_reg_{v}.v", "CLOCK_PORT": "clk", "CLOCK_PERIOD": 100,
        "FP_SIZING": "absolute", "DIE_AREA": [0, 0, die_w, die_h],
        "CORE_AREA": [CORE_X0, CORE_Y0, round(CORE_X0 + core_sites * SITE_W, 2), round(CORE_Y0 + rows * ROW_H, 2)],
        "SYNTH_ELABORATE_ONLY": True, "MACRO_PLACEMENT_CFG": "dir::block.cfg", "FP_PIN_ORDER_CFG": "dir::block_pins.cfg",
        "FP_TAPCELL_DIST": 20, "PL_OPTIMIZE_MIRRORING": False, "RUN_KLAYOUT_DRC": True, "RT_MAX_LAYER": "Metal4",
        "MAX_TRANSITION_CONSTRAINT": 3, "MAX_CAPACITANCE_CONSTRAINT": 0.2, "FP_PDN_VPITCH": 38.87,
        "RUN_CTS": True, "RUN_POST_GPL_DESIGN_REPAIR": False, "RUN_POST_CTS_RESIZER_TIMING": False,
        "RUN_POST_GRT_RESIZER_TIMING": False, "RUN_POST_GRT_DESIGN_REPAIR": False}
    return "\n".join(lines) + "\n", "\n".join(pins) + "\n", json.dumps(lib, indent=1) + "\n", {
        "die_um": [die_w, die_h], "core_sites": core_sites, "rows": rows}


def taps_inside(v, cells, cen, best, ctx):
    W, H = footprint(cells, cen, v)
    out = []
    for rr in range(H):
        r = best["row"] + rr
        for t0, t1 in ctx["blocked"][r]:
            if best["site"] <= t0 and t1 <= best["site"] + W:
                out.append({"rel_row": rr, "rel_site": t0 - best["site"]})
    return out


def generate(args):
    cen = census(); ctx = chip_context()
    nlfile = args.names_netlist
    nlcells = parse_netlist(nlfile)
    nb = neighbour_model(cen)
    files = {}
    blocks = {"a_sdff": build_block("a_sdff")}
    files["max_reg_a_sdff.v"] = netlist_text("a_sdff", blocks["a_sdff"])
    files["max_reg_chip.v"] = chip_rtl_text(blocks["a_sdff"])
    files["max_reg_b_flopcells.v"] = flopcells_text()
    summary = {}
    for v in ("a_sdff", "b_m", "b_ms"):
        if v.startswith("a_"):
            cells = blocks[v]; extra = {}
        else:
            cells, M, S = build_flops(v, nlcells)
            extra = {"names": {"netlist": os.path.relpath(nlfile, HERE) if nlfile.startswith(ROOT) else nlfile,
                               "netlist_sha256": sha(nlfile),
                               "M": {M[k]["q"]: M[k]["inst"] for k in range(N)},
                               "S": {S[k]["q"]: S[k]["inst"] for k in range(N)} if v == "b_ms" else None,
                               "rule": "instance names are the shipped-flow synthesis names of exactly this RTL+config "
                                       "(deterministic flow); regenerate from the run's own synthesized netlist after any "
                                       "change, and post-check by Q net (tools/check_placed.py)"}}
        best, cands, la = choose(v, cells, cen, ctx, nb, args.anchor.get(v))
        W, H = footprint(cells, cen, v)
        hard, soft = anchor_check(cells, cen, ctx, (best["row"], best["site"]), best["order_up"])
        assert not hard, hard
        info = {"variant": v, "footprint": {"width_sites": W, "height_rows": H, "width_um": round(W * SITE_W, 2),
                                            "height_um": round(H * ROW_H, 2)},
                "bounds": bounds(cells, cen, v), "anchor_rule": ANCHOR_RULE[v],
                "chosen_anchor": best, "anchor_soft_m4": soft,
                "legal_anchor_count": len(la), "top_candidates": cands[:8],
                "proxy_note": "ext_hpwl_um: HPWL of boundary nets with free neighbours at their BASELINE positions "
                              "(estimate; GPL re-places them). Used only to rank anchors.",
                "ports": ports(v, cells, cen), "taps_inside": taps_inside(v, cells, cen, best, ctx),
                "cells": [{k: c[k] for k in ("inst", "master", "role", "bit", "rel_row", "rel_site", "mirror", "pins")}
                          for c in cells], **extra}
        d = v + "/"
        files[d + "placement.json"] = json.dumps(info, indent=1) + "\n"
        files[d + "placement.csv"] = csv_text(v, cells, cen, best)
        files[d + "placement.svg"] = svg_text(v, cells, cen, best)
        files[d + "chip_anchor.cfg"] = cfg_text(v, cells, cen, best)
        if v.startswith("a_"):
            bc, bp, bl, binfo = block_files(v, cells, cen)
            files[d + "block.cfg"] = bc; files[d + "block_pins.cfg"] = bp; files[d + "block_librelane.json"] = bl
        else:
            files[d + "names.json"] = json.dumps(extra["names"], indent=1) + "\n"
        summary[v] = {"anchor": best, "footprint": info["footprint"], "bounds": info["bounds"], "legal": len(la)}
    man = {"generator": "gen_placement.py", "generator_sha256": sha(os.path.abspath(__file__)),
           "inputs": {"census.json": sha(CENSUS), "baseline_def": ctx["def_sha256"], "baseline_pnl": sha(BASE_PNL),
                      "names_netlist": [os.path.relpath(nlfile, HERE) if nlfile.startswith(ROOT) else nlfile, sha(nlfile)],
                      "golden_max_reg": sha(GOLDEN)},
           "args": {"anchor": {k: list(v) for k, v in args.anchor.items()}},
           "outputs": {k: hashlib.sha256(v.encode()).hexdigest() for k, v in sorted(files.items())},
           "summary": summary}
    files["MANIFEST.json"] = json.dumps(man, indent=1) + "\n"
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--names-netlist", default=BASE_NL)
    ap.add_argument("--anchor", action="append", default=[], help="V=ROW,SITE")
    args = ap.parse_args()
    args.anchor = {a.split("=")[0]: tuple(int(x) for x in a.split("=")[1].split(",")) for a in args.anchor}
    files = generate(args)
    if args.check:
        bad = [f for f, t in files.items() if not os.path.exists(os.path.join(args.out, f))
               or open(os.path.join(args.out, f)).read() != t]
        print("STALE" if bad else "FRESH", bad)
        sys.exit(1 if bad else 0)
    for f, t in files.items():
        p = os.path.join(args.out, f); os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").write(t)
    s = json.loads(files["MANIFEST.json"])["summary"]
    for v, d in s.items():
        print(v, "anchor", {k: d["anchor"][k] for k in ("row", "site", "order_up", "mirror", "ext_hpwl_um", "internal_hpwl_um")},
              "fp", d["footprint"], "util", d["bounds"]["utilization_box"], "cellA", d["bounds"]["cell_area_um2"], "legal", d["legal"])


if __name__ == "__main__":
    main()
