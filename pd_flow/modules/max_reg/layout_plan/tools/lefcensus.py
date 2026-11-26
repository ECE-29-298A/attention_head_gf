#!/usr/bin/env python3
"""Routing-resource census of the GF180 7-track library for the ripple_add placement.

Tokenizer-based LEF reader (no block regexes). Reads the cell LEF and the nominal tech LEF
from the PDK, asserts the parse is non-degenerate, and prints / writes:
  - site name and size, manufacturing grid;
  - per routing layer: direction, pitch, offset, width, spacing, min area, shortest legal wire;
  - DEF track grid used by the shipped flow (tracks.info);
  - per master: size in sites, symmetry, layers used by pins/OBS (through-track check);
  - per signal pin: on-grid Via1 access points (M2 track x positions, cell-local, orientation N)
    where a default Via1 M1 enclosure fits wholly inside the pin's own Metal1 shapes.
Usage: lefcensus.py [--json OUT] [masters...]
"""
import hashlib, json, os, sys

PDKV = "/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee"
LIBDIR = f"{PDKV}/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0"
CELL_LEF = f"{LIBDIR}/lef/gf180mcu_fd_sc_mcu7t5v0.lef"
TECH_LEF = f"{LIBDIR}/techlef/gf180mcu_fd_sc_mcu7t5v0__nom.tlef"
TRACKS = f"{PDKV}/gf180mcuD/libs.tech/openlane/gf180mcu_fd_sc_mcu7t5v0/tracks.info"
PFX = "gf180mcu_fd_sc_mcu7t5v0__"
EPS = 1e-6


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def tokens(path):
    """LEF tokens; '#' comments dropped; quoted strings kept whole (multi-line)."""
    txt = open(path).read()
    out, i, n = [], 0, len(txt)
    while i < n:
        ch = txt[i]
        if ch == "#":
            while i < n and txt[i] != "\n":
                i += 1
        elif ch == '"':
            j = txt.index('"', i + 1)
            out.append(txt[i:j + 1]); i = j + 1
        elif ch.isspace():
            i += 1
        elif ch == ";":
            out.append(";"); i += 1
        else:
            j = i
            while j < n and not txt[j].isspace() and txt[j] != ";":
                j += 1
            out.append(txt[i:j]); i = j
    return out


def statements(toks, i):
    """Read one ';'-terminated statement starting at i; return (list, next_i)."""
    st = []
    while toks[i] != ";":
        st.append(toks[i]); i += 1
    return st, i + 1


def parse_tech(path):
    """Top-level dispatcher: named blocks (LAYER/VIA/VIARULE/SITE ... END <name>),
    keyword blocks (UNITS/PROPERTYDEFINITIONS ... END <kw>), else ';' statements."""
    t = tokens(path); i = 0
    layers, vias, site, grid = {}, {}, None, None
    while i < len(t):
        k = t[i]
        if k in ("LAYER", "VIA", "VIARULE", "SITE"):
            name = t[i + 1]; i += 2
            while t[i] in ("DEFAULT", "GENERATE"):
                i += 1
            body = []
            while not (t[i] == "END" and t[i + 1] == name):
                st, i = statements(t, i); body.append(st)
            i += 2
            if k == "SITE":
                site = {"name": name}
                for st in body:
                    if st[0] == "SIZE": site["w"], site["h"] = float(st[1]), float(st[3])
                    elif st[0] == "CLASS": site["class"] = st[1]
            elif k == "LAYER":
                d = {"name": name, "spacing": []}
                for st in body:
                    if st[0] == "TYPE": d["type"] = st[1]
                    elif st[0] == "DIRECTION": d["dir"] = st[1]
                    elif st[0] == "PITCH": d["pitch"] = float(st[1])
                    elif st[0] == "OFFSET": d["offset"] = float(st[1])
                    elif st[0] == "WIDTH": d["width"] = float(st[1])
                    elif st[0] == "MINWIDTH": d["minwidth"] = float(st[1])
                    elif st[0] == "AREA": d["area"] = float(st[1])
                    elif st[0] == "SPACING" and len(st) == 2: d["spacing"].append(float(st[1]))
                layers[name] = d
            elif k == "VIA":
                cur, shapes = None, {}
                for st in body:
                    if st[0] == "LAYER": cur = st[1]
                    elif st[0] == "RECT": shapes.setdefault(cur, []).append(tuple(map(float, st[1:5])))
                vias[name] = shapes
        elif k in ("UNITS", "PROPERTYDEFINITIONS"):
            i += 1
            while not (t[i] == "END" and t[i + 1] == k):
                i += 1
            i += 2
        elif k == "END":
            i += 2
        else:
            st, i = statements(t, i)
            if st[0] == "MANUFACTURINGGRID": grid = float(st[1])
    return layers, site, grid, vias


def parse_cells(path):
    t = tokens(path); i = 0; macros = {}
    while i < len(t):
        if t[i] == "MACRO":
            name = t[i + 1]; i += 2
            m = {"name": name, "pins": {}, "obs": [], "sites": []}
            while not (t[i] == "END" and t[i + 1] == name):
                if t[i] == "PIN":
                    pn = t[i + 1]; i += 2; p = {"name": pn, "rects": []}
                    layer = None
                    while not (t[i] == "END" and t[i + 1] == pn):
                        if t[i] == "PORT":
                            i += 1
                            while t[i] != "END":
                                st, i = statements(t, i)
                                if st[0] == "LAYER": layer = st[1]
                                elif st[0] == "RECT":
                                    p["rects"].append((layer, *map(float, st[1:5])))
                            i += 1
                            if t[i] == ";": i += 1
                        else:
                            st, i = statements(t, i)
                            if st[0] == "DIRECTION": p["dir"] = st[1]
                            elif st[0] == "USE": p["use"] = st[1]
                            elif st[0] == "SHAPE": p["shape"] = st[1]
                    i += 2; m["pins"][pn] = p
                elif t[i] == "OBS":
                    i += 1; layer = None
                    while t[i] != "END":
                        st, i = statements(t, i)
                        if st[0] == "LAYER": layer = st[1]
                        elif st[0] == "RECT": m["obs"].append((layer, *map(float, st[1:5])))
                    i += 1
                else:
                    st, i = statements(t, i)
                    if st[0] == "SIZE": m["w"], m["h"] = float(st[1]), float(st[3])
                    elif st[0] == "SITE": m["sites"].append(st[1])
                    elif st[0] == "SYMMETRY": m["symmetry"] = st[1:]
                    elif st[0] == "CLASS": m["class"] = " ".join(st[1:])
            i += 2; macros[name] = m
        else:
            i += 1
    return macros


def covered(rects, x0, y0, x1, y1):
    """Is box [x0,x1]x[y0,y1] covered by the union of axis-aligned rects? (grid sampling at 5 nm)"""
    step = 0.005
    nx = int(round((x1 - x0) / step)); ny = int(round((y1 - y0) / step))
    for a in range(nx + 1):
        x = x0 + a * step
        for b in range(0, ny + 1, max(1, ny // 8)):
            y = y0 + b * step
            if not any(r[0] - EPS <= x <= r[2] + EPS and r[1] - EPS <= y <= r[3] + EPS for r in rects):
                return False
        y = y1
        if not any(r[0] - EPS <= x <= r[2] + EPS and r[1] - EPS <= y <= r[3] + EPS for r in rects):
            return False
    return True


# default Via1 M1 enclosure footprints (from the tech LEF VIA section, asserted in census())
VIA1_M1 = {"HH": (0.19, 0.13), "VV": (0.13, 0.19)}   # half-width, half-height


def access_points(pin, cell_h, xoff=0.28, pitch=0.56, ystep=0.005):
    """M2-track x positions (cell-local, orientation N) with a legal Via1 inside the pin's M1.
    Returns {x: {"via": [...], "y_range": (ymin, ymax), "y_on_m1_track": bool}}."""
    rects = [r[1:] for r in pin["rects"] if r[0] == "Metal1"]
    if not rects:
        return {}
    xmin = min(r[0] for r in rects); xmax = max(r[2] for r in rects)
    ymin = min(r[1] for r in rects); ymax = max(r[3] for r in rects)
    out = {}
    k = 0
    while xoff + k * pitch <= xmax + 0.2:
        x = round(xoff + k * pitch, 3); k += 1
        if x < xmin - 0.2:
            continue
        ys, vias = [], set()
        y = ymin
        while y <= ymax + EPS:
            for v, (hw, hh) in VIA1_M1.items():
                if covered(rects, x - hw, y - hh, x + hw, y + hh):
                    ys.append(round(y, 3)); vias.add(v)
            y += ystep
        if ys:
            m1_tracks = [round(0.28 + 0.56 * j, 3) for j in range(7)]
            on = [yt for yt in m1_tracks if min(ys) - EPS <= yt <= max(ys) + EPS and any(abs(yt - q) < 0.003 for q in ys)]
            out[x] = {"via": sorted(vias), "y_range": (min(ys), max(ys)), "m1_track_ys": on}
    return out


def census(masters, out_json=None):
    layers, site, grid, vias = parse_tech(TECH_LEF)
    # Via1 default enclosures used by access_points() must match the tech LEF
    for v, (hw, hh) in (('Via1_HH', VIA1_M1['HH']), ('Via1_VV', VIA1_M1['VV'])):
        r = vias[v]['Metal1'][0]
        assert abs(r[2] - hw) < EPS and abs(r[3] - hh) < EPS, (v, r)
    macros = parse_cells(CELL_LEF)
    # ---- non-degeneracy asserts
    assert site and site["name"] == "GF018hv5v_mcu_sc7", site
    assert abs(site["w"] - 0.56) < EPS and abs(site["h"] - 3.92) < EPS, site
    for L in ("Metal1", "Metal2", "Metal3", "Metal4", "Metal5"):
        assert L in layers and "pitch" in layers[L] and "dir" in layers[L], (L, layers.get(L))
    assert len(macros) > 200, len(macros)
    rep = {"sources": {"cell_lef": CELL_LEF, "cell_lef_sha256": sha(CELL_LEF),
                       "tech_lef": TECH_LEF, "tech_lef_sha256": sha(TECH_LEF),
                       "tracks_info": TRACKS, "tracks_info_sha256": sha(TRACKS)},
           "site": site, "manufacturing_grid": grid, "layers": {}, "tracks": [], "masters": {}}
    for L in ("Metal1", "Metal2", "Metal3", "Metal4", "Metal5"):
        d = layers[L]
        rep["layers"][L] = {k: d.get(k) for k in ("dir", "pitch", "offset", "width", "minwidth", "area")}
        rep["layers"][L]["spacing"] = min(d["spacing"])
        rep["layers"][L]["shortest_wire_um"] = round(d["area"] / d["width"], 3)
    for line in open(TRACKS):
        f = line.split()
        if len(f) == 4:
            rep["tracks"].append({"layer": f[0], "axis": f[1], "offset": float(f[2]), "pitch": float(f[3])})
    for mname in masters:
        full = mname if mname.startswith(PFX) else PFX + mname
        m = macros[full]
        nsites = m["w"] / site["w"]
        assert abs(nsites - round(nsites)) < 1e-6, (full, m["w"])
        assert abs(m["h"] - site["h"]) < EPS and m["sites"] == [site["name"]], (full, m["h"], m["sites"])
        used = sorted({r[0] for p in m["pins"].values() for r in p["rects"]} | {r[0] for r in m["obs"]})
        e = {"width_um": m["w"], "height_um": m["h"], "sites": int(round(nsites)),
             "area_um2": round(m["w"] * m["h"], 4), "symmetry": m.get("symmetry"),
             "layers_used": used, "metal2_or_above_shapes": any(l in used for l in ("Metal2", "Metal3", "Metal4", "Metal5")),
             "pins": {}}
        for pn, p in m["pins"].items():
            if p.get("use") in ("POWER", "GROUND"):
                e["pins"][pn] = {"use": p["use"], "shape": p.get("shape"),
                                 "layers": sorted({r[0] for r in p["rects"]})}
                continue
            ap = access_points(p, m["h"])
            e["pins"][pn] = {"dir": p.get("dir"),
                             "rects_m1": [r[1:] for r in p["rects"] if r[0] == "Metal1"],
                             "access_x_N": sorted(ap), "access": {str(k): v for k, v in ap.items()},
                             "n_access": len(ap)}
        rep["masters"][full] = e
    if out_json:
        json.dump(rep, open(out_json, "w"), indent=1)
    return rep


def main():
    args = sys.argv[1:]
    out = None
    if args and args[0] == "--json":
        out = args[1]; args = args[2:]
    masters = args or ["addf_1", "addf_2", "addh_1", "xor3_1", "filltie", "endcap", "fill_1", "fill_2"]
    r = census(masters, out)
    print("site", r["site"], "grid", r["manufacturing_grid"])
    print(f"{'layer':7s} dir        pitch offset width space minarea shortest_wire")
    for L, d in r["layers"].items():
        print(f"{L:7s} {d['dir']:10s} {d['pitch']:5.2f} {d['offset']:5.2f} {d['width']:5.3f} {d['spacing']:5.3f} {d['area']:7.4f} {d['shortest_wire_um']:6.3f}")
    print("tracks.info:", [(t["layer"], t["axis"], t["offset"], t["pitch"]) for t in r["tracks"]])
    for m, e in r["masters"].items():
        print(f"\n{m}: {e['width_um']} x {e['height_um']} um = {e['sites']} sites, {e['area_um2']} um2,"
              f" symmetry {e['symmetry']}, layers {e['layers_used']}, M2+ shapes: {e['metal2_or_above_shapes']}")
        for pn, p in e["pins"].items():
            if "use" in p:
                print(f"   {pn:4s} {p['use']} {p['shape']} {p['layers']}")
            else:
                print(f"   {pn:4s} {p['dir']:6s} access M2-track x (N): {p['access_x_N']}  [{p['n_access']}]")

if __name__ == "__main__":
    main()
