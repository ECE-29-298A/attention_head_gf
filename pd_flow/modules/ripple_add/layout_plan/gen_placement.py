#!/usr/bin/env python3
"""ripple_add tetris placement generator (Phase 3, Agent 4). One source of truth for:

  out/ripple_add_n{22,12}.v      gate-level netlist per width (top `ripple_add`, no parameter)
  out/ripple_add_chip.v          chip RTL candidate for src/ripple_add.v (parameterised,
                                 cell branch under `RIPPLE_ADD_CELLS, golden body otherwise)
  out/placement_n{22,12}.csv     relative sub-placement: inst, master, rel_row, rel_site,
                                 orientation for an even / odd anchor row, x/y in um
  out/placement_n{22,12}.json    same plus footprint, ports (side, row, pin, access tracks),
                                 bounds, routing census, HPWL proxy per net class
  out/chip_anchor_n{22,12}.json  absolute placement at the default chip anchor, hierarchical names.
                                 Key "placement", deliberately NOT a MANUAL_GLOBAL_PLACEMENTS config:
                                 that mechanism is REJECTED (measured drift, PLAN.md section 6)
  out/chip_anchor_n{22,12}.cfg   same, MACRO_PLACEMENT_CFG line format (FIRM placement)
  out/placement_n{22,12}.svg     view
  out/block_n{22,12}.json/.cfg   standalone Phase 4 block: die/core, FIRM placement lines in block
  out/block_n{22,12}_pins.cfg    coordinates (2-site endcap column each side), IO pin order
  out/MANIFEST.json              inputs with hashes, arguments, output hashes

Implementation (chosen in PLAN.md): bit i of an N-bit adder is one cell in relative row i:
addf_1 for bits 0..N-2 (carry on CI/CO), xor3_1 for bit N-1 (no carry out). All cells share
relative site 0 (a 33-site column); the MSB cell's slide and pin assignment are searched.

Usage: gen_placement.py [--out DIR] [--check] [--anchor22 ROW,SITE] [--anchor12 ROW,SITE]
  --check   regenerate in memory and fail (exit 1) if any file in DIR differs (stale check).
"""
import argparse, hashlib, io, itertools, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
import lefcensus  # noqa: E402
from defparse import read_def  # noqa: E402

P = "gf180mcu_fd_sc_mcu7t5v0__"
BASE_DEF = os.path.join(HERE, "../../../baseline/harden/def/tt_um_attention_head_gf.def")
SITE_W, ROW_H = 0.56, 3.92
# Chip context (verified against BASE_DEF in chip_context()): core origin and size
CORE_X0, CORE_Y0, CORE_SITES, CORE_ROWS = 3.36, 3.92, 607, 39
INST_PATH = {22: "core.mac.adder", 12: "core.mac.l_adder"}   # mac_unit instance paths
# Default chip anchors (row, site) of relative (0, 0): tap-free and Metal4-stripe-free column
DEFAULT_ANCHOR = {22: (1, 107), 12: (23, 107)}
# Net-class weights for the wire proxy (relative toggle rate x glitch; explore/activity.json)
W_CLASS = {"carry": 1.25, "a": 1.0, "b": 1.0, "s": 1.0, "cin": 0.5}


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


# ----------------------------------------------------------------------------- geometry
def orient_xy(x, y, w, orient):
    if orient == "N": return x, y
    if orient == "FS": return x, ROW_H - y
    if orient == "FN": return w - x, y
    if orient == "S": return w - x, ROW_H - y
    raise ValueError(orient)


def row_orient(abs_row):
    return "N" if abs_row % 2 == 0 else "FS"


def mirror(o):
    return {"N": "FN", "FS": "S", "FN": "N", "S": "FS"}[o]


def pin_access(cen, master, pin, orient):
    """Access points of `pin` in cell-local coordinates after orientation: list of (x, y)."""
    m = cen["masters"][P + master]
    p = m["pins"][pin]
    pts = []
    for xs, a in p["access"].items():
        x = float(xs)
        ys = a["m1_track_ys"] or [round((a["y_range"][0] + a["y_range"][1]) / 2, 3)]
        for y in ys:
            pts.append(orient_xy(x, y, m["width_um"], orient))
    return pts


def pin_center(cen, master, pin, orient):
    pts = pin_access(cen, master, pin, orient)
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


# ----------------------------------------------------------------------------- design
def build_cells(n, cen):
    """Cell records of the column grammar, before the MSB search."""
    cells = []
    for i in range(n - 1):
        cells.append({"inst": f"bitslice[{i}].u_fa", "master": "addf_1", "bit": i, "role": "fa",
                      "rel_row": i, "rel_site": 0, "mirror": False,
                      "pins": {"a": "A", "b": "B", "c_in": "CI", "s": "S", "c_out": "CO"}})
    cells.append({"inst": "u_msb_x3", "master": "xor3_1", "bit": n - 1, "role": "msb",
                  "rel_row": n - 1, "rel_site": 0, "mirror": False,
                  "pins": {"a": "A1", "b": "A2", "c_in": "A3", "s": "Z"}})
    return cells


def width_sites(cen, master):
    return cen["masters"][P + master]["sites"]


def footprint(cells, cen):
    w = max(c["rel_site"] + width_sites(cen, c["master"]) for c in cells)
    h = max(c["rel_row"] for c in cells) + 1
    return w, h


def abs_pin_xy(c, pin, cen, anchor_row, use_center=True):
    """Pin position in footprint-relative um for a given anchor-row parity."""
    o = row_orient(anchor_row + c["rel_row"])
    if c["mirror"]: o = mirror(o)
    px, py = pin_center(cen, c["master"], pin, o)
    return c["rel_site"] * SITE_W + px, c["rel_row"] * ROW_H + py


def nets_proxy(cells, cen, anchor_row, n):
    """Per-class HPWL proxy (um) with ports on the footprint edges: a_i, s_i west (x=0),
    b_i east (x=W), cin south at bit 0. Uses access-point centroids, not cell centres."""
    W, _ = footprint(cells, cen)
    Wum = W * SITE_W
    byb = {c["bit"]: c for c in cells}
    out = {k: 0.0 for k in W_CLASS}
    per = []
    for i in range(n):
        c = byb[i]; yc = c["rel_row"] * ROW_H + ROW_H / 2
        ax, ay = abs_pin_xy(c, c["pins"]["a"], cen, anchor_row)
        bx, by = abs_pin_xy(c, c["pins"]["b"], cen, anchor_row)
        sx, sy = abs_pin_xy(c, c["pins"]["s"], cen, anchor_row)
        d = {"a": ax + abs(ay - yc), "b": (Wum - bx) + abs(by - yc), "s": sx + abs(sy - yc)}
        if i == 0:
            cx, cy = abs_pin_xy(c, c["pins"]["c_in"], cen, anchor_row)
            d["cin"] = cy
        else:
            p = byb[i - 1]
            x0, y0 = abs_pin_xy(p, p["pins"]["c_out"], cen, anchor_row)
            x1, y1 = abs_pin_xy(c, c["pins"]["c_in"], cen, anchor_row)
            d["carry"] = abs(x1 - x0) + abs(y1 - y0)
        for k, v in d.items():
            out[k] += v
        per.append({"bit": i, **{k: round(v, 3) for k, v in d.items()}})
    score = sum(W_CLASS[k] * v for k, v in out.items())
    return {"by_class_um": {k: round(v, 3) for k, v in out.items()}, "weighted_score": round(score, 3),
            "per_bit": per, "weights": W_CLASS}


MSB_CARRY_PIN = "A3"   # fixed, not searched: see search_msb


def search_msb(cells, cen, n):
    """Discrete search for the MSB xor3_1: slide (rel_site), mirror, and the a/b assignment over
    {A1, A2}. The score is evaluated for both anchor parities and summed (parity-proof).

    The carry is FIXED on A3. Pin access may only choose among inputs that are equivalent in timing
    and energy, and the xor3_1 inputs are not: A3 feeds only the last XOR stage, so A3->Z is the fast
    arc (Liberty ss_125C_3v00 about 0.3-1.5 ns against about 1.4-3.4 ns for A1/A2->Z), and a
    glitching carry on A3 toggles fewer internal nodes. Measured on the chip's ss worst path:
    carry on A3 (run hyb) 1.597 ns arc, WNS 26.12 ns; carry on A1 (runs final / final_fixed, an
    earlier version of this search that minimised the HPWL proxy only) 3.545 / 3.585 ns arc,
    WNS 23.69 / 23.16 ns (layout_review/msb_arc_evidence.txt). The HPWL proxy only breaks ties."""
    msb = cells[-1]
    W = width_sites(cen, "addf_1"); wm = width_sites(cen, "xor3_1")
    best = None
    for site in range(0, W - wm + 1):
        for mir in (False, True):
            for ab in itertools.permutations(["A1", "A2"]):
                perm = (ab[0], ab[1], MSB_CARRY_PIN)
                msb.update(rel_site=site, mirror=mir,
                           pins={"a": perm[0], "b": perm[1], "c_in": perm[2], "s": "Z"})
                sc = nets_proxy(cells, cen, 0, n)["weighted_score"] + nets_proxy(cells, cen, 1, n)["weighted_score"]
                key = (round(sc, 6), site, mir, perm)
                if best is None or key < best[0]:
                    best = (key, site, mir, perm)
    _, site, mir, perm = best
    msb.update(rel_site=site, mirror=mir, pins={"a": perm[0], "b": perm[1], "c_in": perm[2], "s": "Z"})
    return {"rel_site": site, "mirror": mir, "pins": msb["pins"]}


def bounds(cells, cen):
    """Area floor, hard minimum, feasibility floor per row count, unfolded width (sites)."""
    widths = [width_sites(cen, c["master"]) for c in cells]
    total = sum(widths)
    res = {"site_rows_total": total, "widest_cell_sites": max(widths), "per_rows": []}
    for R in sorted({len(cells), (len(cells) + 1) // 2, 8, 6, 4, 2, 1}, reverse=True):
        floor = -(-total // R)
        # feasibility: rows hold whole cells; greedy first-fit-decreasing over increasing width
        wsorted = sorted(widths, reverse=True)
        W = max(floor, max(widths))
        while True:
            rows = [0] * R
            ok = True
            for w in wsorted:
                j = min(range(R), key=lambda k: rows[k])
                if rows[j] + w > W:
                    ok = False; break
                rows[j] += w
            if ok: break
            W += 1
        res["per_rows"].append({"rows": R, "area_floor_sites": floor, "feasibility_floor_sites": W,
                                "utilization_at_feasibility": round(total / (W * R), 4)})
    res["unfolded_one_row_sites"] = total
    return res


def chip_context():
    """Taps/endcaps (FIXED, design independent) and Metal4 PDN stripes from the baseline DEF."""
    comps, _, dbu = read_def(BASE_DEF)
    txt = open(BASE_DEF).read()
    import re
    rows = re.findall(r"^ROW ROW_(\d+) (\S+) (\d+) (\d+) (\S+) DO (\d+) BY 1 STEP (\d+) 0 ;", txt, re.M)
    assert len(rows) == CORE_ROWS, len(rows)
    for r, site, x, y, o, cnt, step in rows:
        assert site == "GF018hv5v_mcu_sc7" and int(x) / dbu == CORE_X0 and int(cnt) == CORE_SITES
        assert abs(int(y) / dbu - (CORE_Y0 + int(r) * ROW_H)) < 1e-9 and o == row_orient(int(r)), (r, y, o)
        assert int(step) / dbu == SITE_W
    blocked = {r: [] for r in range(CORE_ROWS)}   # (site0, site1) occupied by FIXED physical cells
    for name, cdat in comps.items():
        if cdat["status"] == "FIXED" and ("filltie" in cdat["master"] or "endcap" in cdat["master"]):
            r = int(round((cdat["y"] - CORE_Y0) / ROW_H)); s0 = int(round((cdat["x"] - CORE_X0) / SITE_W))
            blocked[r].append((s0, s0 + 2))
    stripes = []
    sec = txt[txt.index("SPECIALNETS"):txt.index("END SPECIALNETS")]
    cur = None
    for line in sec.splitlines():
        m = re.match(r"\s*- (\S+)", line)
        if m: cur = m.group(1)
        for w, x in re.findall(r"Metal4 (\d+) \+ SHAPE STRIPE \( (\d+) \d+ \)", line):
            stripes.append({"net": cur, "x_center": int(x) / dbu, "width": int(w) / dbu})
    return {"rows": [{"row": int(r), "orient": o} for r, _, _, _, o, _, _ in rows], "blocked": blocked,
            "m4_stripes": sorted(stripes, key=lambda s: s["x_center"]), "def": os.path.relpath(BASE_DEF, HERE),
            "def_sha256": sha(BASE_DEF)}


def anchor_checks(cells, cen, ctx, anchor):
    """Hard: inside core, no overlap with FIXED taps/endcaps. Soft: clear of M4 stripes (+0.28 um)."""
    r0, s0 = anchor
    hard, soft = [], []
    for c in cells:
        r = r0 + c["rel_row"]; a = s0 + c["rel_site"]; b = a + width_sites(cen, c["master"])
        if not (0 <= r < CORE_ROWS and 0 <= a and b <= CORE_SITES):
            hard.append(f"{c['inst']} outside core (row {r}, sites {a}-{b})")
            continue
        for t0, t1 in ctx["blocked"][r]:
            if a < t1 and t0 < b:
                hard.append(f"{c['inst']} overlaps FIXED tap/endcap at row {r} sites {t0}-{t1}")
        x0 = CORE_X0 + a * SITE_W; x1 = CORE_X0 + b * SITE_W
        for st in ctx["m4_stripes"]:
            if x0 < st["x_center"] + st["width"] / 2 + 0.28 and st["x_center"] - st["width"] / 2 - 0.28 < x1:
                soft.append(f"{c['inst']} under M4 {st['net']} stripe x={st['x_center']}")
    return hard, soft


def legal_anchors(cells, cen, ctx):
    W, H = footprint(cells, cen)
    out = []
    for r0 in range(0, CORE_ROWS - H + 1):
        for s0 in range(0, CORE_SITES - W + 1):
            hard, soft = anchor_checks(cells, cen, ctx, (r0, s0))
            if not hard:
                out.append({"row": r0, "site": s0, "stripe_free": not soft})
    return out


# ----------------------------------------------------------------------------- census
def routing_census(cells, cen, n):
    """Per-row track supply and in-footprint demand (estimate, before routing)."""
    W, H = footprint(cells, cen)
    m2_per_row = W                      # vertical tracks over the footprint (one per site column)
    m3_per_row = int(round(ROW_H / 0.56))
    rows = []
    for c in cells:
        # horizontal (M3) segments inside the footprint, from pin access centroids (parity 0)
        segs = []
        ax, _ = abs_pin_xy(c, c["pins"]["a"], cen, 0); sx, _ = abs_pin_xy(c, c["pins"]["s"], cen, 0)
        bx, _ = abs_pin_xy(c, c["pins"]["b"], cen, 0)
        segs += [("a", 0.0, ax), ("s", 0.0, sx), ("b", bx, W * SITE_W)]
        if c["bit"] > 0:
            p = [q for q in cells if q["bit"] == c["bit"] - 1][0]
            x0, _ = abs_pin_xy(p, p["pins"]["c_out"], cen, 0); x1, _ = abs_pin_xy(c, c["pins"]["c_in"], cen, 0)
            segs.append(("carry", min(x0, x1), max(x0, x1)))
        # max overlap of horizontal segments = M3 tracks needed in this row
        ev = sorted([(a, 1) for _, a, b in segs if b - a > 1e-6] + [(b, -1) for _, a, b in segs if b - a > 1e-6])
        cur = mx = 0
        for _, d in ev:
            cur += d; mx = max(mx, cur)
        pins = sum(1 for _ in c["pins"])
        rows.append({"rel_row": c["rel_row"], "signal_pins": pins, "m3_tracks_needed_est": mx,
                     "m3_tracks_free_est": m3_per_row - mx, "m2_tracks": m2_per_row,
                     "m2_tracks_for_pin_access_est": pins})
    return {"m2_tracks_per_row": m2_per_row, "m3_tracks_per_row": m3_per_row,
            "m4_tracks_over_footprint": W, "metal1": "pin access and rails only (RT_MIN_LAYER Metal2)",
            "through_tracks": "no master in this block has Metal2+ shapes: every M2/M3/M4 track crosses every cell",
            "scarce_direction": "horizontal (M3): 7 tracks per row; the column is 33 sites wide, 1 cell per row",
            "rows": rows}


# ----------------------------------------------------------------------------- emitters
def netlist_text(n, cells):
    msb = cells[-1]["pins"]
    pm = {msb["a"]: f"a[{n-1}]", msb["b"]: f"b[{n-1}]", msb["c_in"]: f"c[{n-1}]"}
    return f"""// ripple_add, N={n}: gate-level netlist (GF180 7-track), generated by
// pd_flow/modules/ripple_add/layout_plan/gen_placement.py. Do not edit.
// Bits 0..{n-2}: addf_1 (carry on CI/CO); bit {n-1}: xor3_1 (no carry out).
// Instance names (stable, identical to the flattened chip names under the adder instance):
//   bitslice[i].u_fa (i = 0..{n-2}), u_msb_x3.
module ripple_add (
    input  wire [{n-1}:0] a,
    input  wire [{n-1}:0] b,
    input  wire        cin,
    output wire [{n-1}:0] s
);
    localparam N = {n};
    wire [N-1:0] c;
    assign c[0] = cin;
    genvar i;
    generate
        for (i = 0; i < N - 1; i = i + 1) begin : bitslice
            {P}addf_1 u_fa (.A(a[i]), .B(b[i]), .CI(c[i]), .S(s[i]), .CO(c[i + 1]));
        end
    endgenerate
    {P}xor3_1 u_msb_x3 (.A1({pm['A1']}), .A2({pm['A2']}), .A3({pm['A3']}), .Z(s[{n-1}]));
endmodule
"""


def chip_rtl_text(cells22, cells12):
    def msbline(cells, w):
        m = cells[-1]["pins"]
        pm = {m["a"]: "a[N-1]", m["b"]: "b[N-1]", m["c_in"]: "c[N-1]"}
        return f"{P}xor3_1 u_msb_x3 (.A1({pm['A1']}), .A2({pm['A2']}), .A3({pm['A3']}), .Z(s[N-1]));"
    assert msbline(cells22, 22) == msbline(cells12, 12), "MSB pin assignment must agree for one RTL"
    return f"""/*
Shared by accum and score_mac.
*/

// Hand-written ripple-carry adder: N full adders chained, carry out dropped (wraps like +).
// Phase 3 candidate (generated by pd_flow/modules/ripple_add/layout_plan/gen_placement.py):
// with `RIPPLE_ADD_CELLS defined (set only through VERILOG_DEFINES in the harden config) the adder
// is instantiated GF180 7-track cells with stable names (bitslice[i].u_fa = addf_1 for bits 0..N-2,
// u_msb_x3 = xor3_1 for bit N-1, carry on A3). Without the define, every simulator, linter and
// synthesis run compiles the original behavioural body below.
module ripple_add #(parameter N = 16) (
    input  wire [N-1:0] a,
    input  wire [N-1:0] b,
    input  wire         cin,
    output wire [N-1:0] s
);
`ifdef RIPPLE_ADD_CELLS
    wire [N-1:0] c;
    assign c[0] = cin;
    genvar i;
    generate
        for (i = 0; i < N - 1; i = i + 1) begin : bitslice
            {P}addf_1 u_fa (.A(a[i]), .B(b[i]), .CI(c[i]), .S(s[i]), .CO(c[i + 1]));
        end
    endgenerate
    {msbline(cells22, 22)}
`else
    wire [N:0] c;
    assign c[0] = cin;
    genvar i;
    generate
        for (i = 0; i < N; i = i + 1) begin : fa
            assign s[i]     = a[i] ^ b[i] ^ c[i];
            assign c[i + 1] = (a[i] & b[i]) | (c[i] & (a[i] ^ b[i]));
        end
    endgenerate
`endif
endmodule
"""


def placement_rows(cells, cen):
    out = []
    for c in cells:
        w = width_sites(cen, c["master"])
        oe = row_orient(c["rel_row"]); oo = row_orient(c["rel_row"] + 1)
        if c["mirror"]: oe, oo = mirror(oe), mirror(oo)
        out.append({"inst": c["inst"], "master": P + c["master"], "bit": c["bit"], "role": c["role"],
                    "rel_row": c["rel_row"], "rel_site": c["rel_site"], "width_sites": w,
                    "orient_even_anchor": oe, "orient_odd_anchor": oo,
                    "rel_x_um": round(c["rel_site"] * SITE_W, 3), "rel_y_um": round(c["rel_row"] * ROW_H, 3),
                    "pins": c["pins"]})
    return out


def csv_text(rows):
    f = io.StringIO()
    f.write("inst,master,bit,role,rel_row,rel_site,width_sites,orient_even_anchor,orient_odd_anchor,rel_x_um,rel_y_um\n")
    for r in rows:
        f.write(",".join(str(r[k]) for k in ("inst", "master", "bit", "role", "rel_row", "rel_site", "width_sites",
                                             "orient_even_anchor", "orient_odd_anchor", "rel_x_um", "rel_y_um")) + "\n")
    return f.getvalue()


def ports(cells, cen, n):
    """Boundary contract: side, row, cell pin and its access tracks (cell-local x, N)."""
    out = []
    for c in cells:
        for net, side in (("a", "W"), ("s", "W"), ("b", "E")):
            pin = c["pins"][net]
            ax = cen["masters"][P + c["master"]]["pins"][pin]["access_x_N"]
            out.append({"port": f"{net}[{c['bit']}]", "side": side, "rel_row": c["rel_row"], "inst": c["inst"],
                        "pin": pin, "access_tracks_cell_local_x_N": ax, "mirror": c["mirror"]})
        if c["bit"] == 0:
            pin = c["pins"]["c_in"]
            out.append({"port": "cin", "side": "S", "rel_row": 0, "inst": c["inst"], "pin": pin,
                        "access_tracks_cell_local_x_N": cen["masters"][P + c["master"]]["pins"][pin]["access_x_N"],
                        "mirror": c["mirror"]})
    return out


def chip_anchor(cells, cen, n, anchor):
    r0, s0 = anchor
    mgp, cfg = {}, []
    for c in cells:
        r = r0 + c["rel_row"]; o = row_orient(r)
        if c["mirror"]: o = mirror(o)
        x = round(CORE_X0 + (s0 + c["rel_site"]) * SITE_W, 3); y = round(CORE_Y0 + r * ROW_H, 3)
        name = f"{INST_PATH[n]}.{c['inst']}"
        mgp[name] = {"location": [x, y], "orientation": o}
        cfg.append(f"{name} {x:.2f} {y:.2f} {o}")
    return mgp, "\n".join(cfg) + "\n"


def svg_text(cells, cen, n, anchor_row):
    W, H = footprint(cells, cen)
    sc = 8.0; pad = 40
    wpx = W * SITE_W * sc + 2 * pad; hpx = H * ROW_H * sc + 2 * pad
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{wpx:.0f}" height="{hpx:.0f}" font-family="monospace" font-size="9">',
         f'<rect x="0" y="0" width="{wpx:.0f}" height="{hpx:.0f}" fill="white"/>']
    def X(x): return pad + x * sc
    def Y(y): return pad + (H * ROW_H - y) * sc
    for r in range(H + 1):
        o.append(f'<line x1="{X(0)}" y1="{Y(r*ROW_H)}" x2="{X(W*SITE_W)}" y2="{Y(r*ROW_H)}" stroke="#bbb" stroke-width="1"/>')
    for c in cells:
        w = width_sites(cen, c["master"]) * SITE_W
        x0 = c["rel_site"] * SITE_W; y0 = c["rel_row"] * ROW_H
        fill = "#cfe3ff" if c["role"] == "fa" else "#ffe0b3"
        o.append(f'<rect x="{X(x0)}" y="{Y(y0+ROW_H)}" width="{w*sc}" height="{ROW_H*sc}" fill="{fill}" stroke="#333"/>')
        ori = row_orient(anchor_row + c["rel_row"]); ori = mirror(ori) if c["mirror"] else ori
        o.append(f'<text x="{X(x0)+3}" y="{Y(y0+ROW_H)+10}">{c["inst"]} {c["master"]} {ori}</text>')
        for net, pin in c["pins"].items():
            px, py = abs_pin_xy(c, pin, cen, anchor_row)
            col = {"a": "#c00", "b": "#06c", "s": "#090", "c_in": "#a0a", "c_out": "#a0a"}[net]
            o.append(f'<circle cx="{X(px)}" cy="{Y(py)}" r="2.5" fill="{col}"/>')
            o.append(f'<text x="{X(px)+3}" y="{Y(py)-2}" fill="{col}">{pin}</text>')
    for i in range(1, n):
        p = cells[i - 1]; c = cells[i]
        x0, y0 = abs_pin_xy(p, p["pins"]["c_out"], cen, anchor_row); x1, y1 = abs_pin_xy(c, c["pins"]["c_in"], cen, anchor_row)
        o.append(f'<polyline points="{X(x0)},{Y(y0)} {X(x0)},{Y(y1)} {X(x1)},{Y(y1)}" fill="none" stroke="#a0a" stroke-width="1.5"/>')
    o.append(f'<text x="4" y="{hpx/2}">W: a,s</text><text x="{wpx-40}" y="{hpx/2}">E: b</text>')
    o.append(f'<text x="{wpx/2}" y="{hpx-8}">S: cin (bit 0)   rows: anchor parity {anchor_row % 2}</text>')
    o.append("</svg>")
    return "\n".join(o) + "\n"


BLOCK_ENDCAP_SITES, BLOCK_MX, BLOCK_MY = 2, 3.36, 3.92   # endcap width (LEF: 2 sites); die margins


def block_view(cells, cen, n):
    """Standalone block for Phase 4: core = endcap + footprint + endcap, rows start with N."""
    W, H = footprint(cells, cen)
    cw = (W + 2 * BLOCK_ENDCAP_SITES) * SITE_W; ch = H * ROW_H
    die = [0, 0, round(cw + 2 * BLOCK_MX, 3), round(ch + 2 * BLOCK_MY, 3)]
    core = [BLOCK_MX, BLOCK_MY, round(BLOCK_MX + cw, 3), round(BLOCK_MY + ch, 3)]
    lines = []
    for c in cells:
        o = row_orient(c["rel_row"]); o = mirror(o) if c["mirror"] else o
        x = BLOCK_MX + (BLOCK_ENDCAP_SITES + c["rel_site"]) * SITE_W; y = BLOCK_MY + c["rel_row"] * ROW_H
        lines.append(f"{c['inst']} {x:.2f} {y:.2f} {o}")
    esc = lambda t: t.replace("[", "\\[").replace("]", "\\]")
    pins = ["#S", "cin", "#W"] + [esc(f"{k}[{i}]") for i in range(n) for k in ("a", "s")] + \
           ["#E"] + [esc(f"b[{i}]") for i in range(n)]
    info = {"N": n, "DIE_AREA": die, "CORE_AREA": core, "rows": H, "sites_per_row": W + 2 * BLOCK_ENDCAP_SITES,
            "endcap_sites_each_side": BLOCK_ENDCAP_SITES,
            "note": "rows alternate N (row 0) / FS; cells keep the relative placement at anchor parity 0"}
    return info, "\n".join(lines) + "\n", "\n".join(pins) + "\n"


def block_config(n, binfo):
    """Phase 4 starting config (UNTESTED template: Phase 4 owns and records every deviation).
    Paths are relative to a run directory holding copies of out/ files."""
    return {
        "//": "UNTESTED Phase 4 template generated by gen_placement.py. Standalone ripple_add block, "
              "placement FIRM from block_n%d.cfg, routing automatic. See PLAN.md section 7." % n,
        "//deviation_1_pdn": "The block is %.2f um wide, narrower than the 38.87 um stripe pitch, so one "
              "Metal4 VPWR/VGND stripe pair WILL lie over the column (unlike the chip anchors, which are "
              "stripe-free). Harmless for function (no cell has Metal2+ shapes) but it removes M4 tracks; "
              "record it when comparing routing with chip context." % binfo["DIE_AREA"][2],
        "//deviation_2_taps": "No tap cells inside the block: FP_TAPCELL_DIST is set above the row width, "
              "so the only well ties are the 2-site endcaps at both row ends. The 5 V rule DF.13_MV/DF.14_MV "
              "allows at most 15 um to a tie; the farthest column point is about 9.5 um from an endcap. "
              "This differs from the chip (staggered filltie checkerboard, worst 10.3 um via the "
              "neighbour row) and must be confirmed with KLayout DRC (feol=true), since Magic does not check it.",
        "FP_TAPCELL_DIST": 100,
        "DESIGN_NAME": "ripple_add",
        "VERILOG_FILES": [f"dir::ripple_add_n{n}.v"],
        "SYNTH_ELABORATE_ONLY": True,
        "CLOCK_PORT": None, "CLOCK_PERIOD": 100,
        "FP_SIZING": "absolute", "DIE_AREA": binfo["DIE_AREA"], "CORE_AREA": binfo["CORE_AREA"],
        "MACRO_PLACEMENT_CFG": f"dir::block_n{n}.cfg",
        "IO_PIN_ORDER_CFG": f"dir::block_n{n}_pins.cfg",
        "IO_PIN_H_LAYER": "Metal3", "IO_PIN_V_LAYER": "Metal2",
        "RUN_CTS": False, "RUN_POST_GPL_DESIGN_REPAIR": False, "RUN_POST_CTS_RESIZER_TIMING": False,
        "RUN_POST_GRT_DESIGN_REPAIR": False, "RUN_POST_GRT_RESIZER_TIMING": False,
        "PL_OPTIMIZE_MIRRORING": False,
        "RT_MIN_LAYER": "Metal2", "RT_MAX_LAYER": "Metal4", "GRT_ALLOW_CONGESTION": False,
        "PDN_VPITCH": 38.87, "PDN_MULTILAYER": False,
        "RUN_KLAYOUT_DRC": True, "MAGIC_DEF_LABELS": False,
    }


# ----------------------------------------------------------------------------- main
def generate(args):
    cen = lefcensus.census(["addf_1", "xor3_1", "filltie", "endcap", "fill_1", "fill_2"])
    ctx = chip_context()
    files, design = {}, {}
    for n in (22, 12):
        cells = build_cells(n, cen)
        msb = search_msb(cells, cen, n)
        W, H = footprint(cells, cen)
        anchor = args[f"anchor{n}"]
        hard, soft = anchor_checks(cells, cen, ctx, anchor)
        if hard:
            raise SystemExit(f"anchor {anchor} for N={n} illegal: {hard[:3]}")
        la = legal_anchors(cells, cen, ctx)
        rows = placement_rows(cells, cen)
        used = sum(r["width_sites"] for r in rows)
        info = {"N": n, "implementation": "addf_1 x (N-1) + xor3_1 MSB, one bit per row (column)",
                "footprint": {"width_sites": W, "height_rows": H, "width_um": round(W * SITE_W, 3),
                              "height_um": round(H * ROW_H, 3), "bbox_area_um2": round(W * SITE_W * H * ROW_H, 4),
                              "cell_area_um2": round(sum(cen["masters"][P + c["master"]]["area_um2"] for c in cells), 4),
                              "site_rows_used": used, "utilization": round(used / (W * H), 4),
                              "free_sites": [{"rel_row": r["rel_row"], "sites": W - r["width_sites"],
                                              "range": [r["rel_site"] + r["width_sites"], W] if r["rel_site"] == 0 else [0, r["rel_site"]]}
                                             for r in rows if r["width_sites"] < W]},
                "msb_search": msb, "ports": ports(cells, cen, n), "bounds": bounds(cells, cen),
                "hpwl_proxy_even_anchor": nets_proxy(cells, cen, 0, n),
                "hpwl_proxy_odd_anchor": nets_proxy(cells, cen, 1, n),
                "routing_census": routing_census(cells, cen, n),
                "default_chip_anchor": {"row": anchor[0], "site": anchor[1], "inst_path": INST_PATH[n],
                                        "soft_warnings": soft},
                "legal_chip_anchors_count": len(la),
                "legal_chip_anchors_stripe_free": [a for a in la if a["stripe_free"]],
                "legal_chip_anchors_note": "count = all tap/endcap/core-legal anchors (the hard rule). "
                    "stripe_free is a SOFT preference only: every pin is on Metal1 and the M4 stripes cross "
                    "every row anyway; do not use it to shrink the tetris search space.",
                "cells": rows}
        design[n] = (cells, info)
        files[f"ripple_add_n{n}.v"] = netlist_text(n, cells)
        files[f"placement_n{n}.csv"] = csv_text(rows)
        files[f"placement_n{n}.json"] = json.dumps(info, indent=1) + "\n"
        mgp, cfg = chip_anchor(cells, cen, n, anchor)
        files[f"chip_anchor_n{n}.json"] = json.dumps({
            "status": "REFERENCE ONLY. Do not paste into MANUAL_GLOBAL_PLACEMENTS: rejected, measured drift "
                      "(2/34 cells off target by up to 20.7 um, 21/34 mirrored after detailed placement; "
                      "chip_runs/placement_effect.json). Integrate with chip_anchor_n%d.cfg via MACRO_PLACEMENT_CFG." % n,
            "placement": mgp}, indent=1) + "\n"
        files[f"chip_anchor_n{n}.cfg"] = cfg
        files[f"placement_n{n}.svg"] = svg_text(cells, cen, n, anchor[0])
        binfo, bcfg, bpins = block_view(cells, cen, n)
        files[f"block_n{n}.json"] = json.dumps(binfo, indent=1) + "\n"
        files[f"block_n{n}.cfg"] = bcfg
        files[f"block_n{n}_pins.cfg"] = bpins
        files[f"block_n{n}_librelane.json"] = json.dumps(block_config(n, binfo), indent=1) + "\n"
    files["ripple_add_chip.v"] = chip_rtl_text(design[22][0], design[12][0])
    files["census_summary.json"] = json.dumps({"site": cen["site"], "layers": cen["layers"], "tracks": cen["tracks"],
                                               "sources": cen["sources"],
                                               "masters": {m: {k: v for k, v in e.items() if k != "pins"} |
                                                           {"pins": {p: {kk: vv for kk, vv in d.items() if kk in ("dir", "use", "access_x_N", "n_access", "shape")}
                                                                     for p, d in e["pins"].items()}}
                                                           for m, e in cen["masters"].items()},
                                               "chip_context": {"def": ctx["def"], "def_sha256": ctx["def_sha256"],
                                                                "m4_stripes": ctx["m4_stripes"],
                                                                "tap_rows_dense": [r for r, b in ctx["blocked"].items() if len(b) > 12]}},
                                              indent=1) + "\n"
    manifest = {"generator": "gen_placement.py", "generator_sha256": sha(os.path.abspath(__file__)),
                "args": {"anchor22": list(args["anchor22"]), "anchor12": list(args["anchor12"])},
                "inputs": {**cen["sources"], "baseline_def": ctx["def"], "baseline_def_sha256": ctx["def_sha256"],
                           "lefcensus_sha256": sha(os.path.join(HERE, "lefcensus.py"))},
                "outputs": {k: hashlib.sha256(v.encode()).hexdigest() for k, v in sorted(files.items())}}
    files["MANIFEST.json"] = json.dumps(manifest, indent=1) + "\n"
    return files


def parse_anchor(s):
    r, c = s.split(","); return int(r), int(c)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--anchor22", type=parse_anchor, default=DEFAULT_ANCHOR[22])
    ap.add_argument("--anchor12", type=parse_anchor, default=DEFAULT_ANCHOR[12])
    a = ap.parse_args()
    files = generate({"anchor22": a.anchor22, "anchor12": a.anchor12})
    if a.check:
        bad = []
        for k, v in files.items():
            p = os.path.join(a.out, k)
            if not os.path.exists(p) or open(p).read() != v:
                bad.append(k)
        extra = sorted(set(os.listdir(a.out)) - set(files) - {"validation.json"}) if os.path.isdir(a.out) else []
        print("STALE" if bad else "FRESH", bad, "unexpected files:", extra)
        sys.exit(1 if bad or extra else 0)
    frozen = os.path.join(HERE, "out")
    if os.path.abspath(a.out) == frozen and (a.anchor22 != DEFAULT_ANCHOR[22] or a.anchor12 != DEFAULT_ANCHOR[12]):
        raise SystemExit("refusing to write a non-default variant over the frozen handoff out/; use --out")
    os.makedirs(a.out, exist_ok=True)
    for k, v in files.items():
        open(os.path.join(a.out, k), "w").write(v)
    print("wrote", len(files), "files to", a.out)


if __name__ == "__main__":
    main()
