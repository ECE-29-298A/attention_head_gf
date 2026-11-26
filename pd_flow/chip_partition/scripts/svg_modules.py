#!/usr/bin/env python3
"""svg_modules.py <def> <attribution.json> <out.svg> [title] [--regions regions.json]

Draws a placed DEF to scale, cells coloured by in-context module (attrib.py), with taps,
endcaps, repair and clock cells distinguished, and optional floorplan region outlines.
Coordinates are the DEF's own (um); nothing is estimated.
"""
import json, os, sys, html
sys.path.insert(0, os.path.dirname(__file__))
import pdlib

COL = {"FE": "#7b4bb7", "CTRL": "#d1495b", "MAC": "#2f6fb5", "EXP": "#e0a030", "MAX": "#2a9d8f",
       "DIV": "#6a994e", "shared": "#999999", "repair": "#f05d23", "CLKTREE": "#111111", "tie": "#c0c0c0",
       "tap": "#e4e4e4"}


def colour(m):
    if m.startswith("shared"):
        return COL["shared"]
    if m.startswith("repair"):
        return COL["repair"]
    if m.startswith("tie"):
        return COL["tie"]
    return COL.get(m, "#bbbbbb")


def main():
    a = sys.argv[1:]
    regions = None
    if "--regions" in a:
        i = a.index("--regions")
        regions = json.load(open(a[i + 1]))
        del a[i:i + 2]
    fdef, attr, out = a[0], a[1], a[2]
    title = a[3] if len(a) > 3 else os.path.basename(fdef)
    D = pdlib.parse_def(fdef, want_routes=False)
    L = pdlib.lef_macros()
    mod = json.load(open(attr))["module_of_cell"] if attr != "-" else {}
    x0, y0, x1, y1 = D["die"]
    S = 4.0  # px per um
    W, H = (x1 - x0) * S, (y1 - y0) * S
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H + 60:.0f}" width="{W:.0f}" '
         f'height="{H + 60:.0f}" font-family="Helvetica,Arial,sans-serif">',
         f'<rect x="0" y="0" width="{W:.0f}" height="{H + 60:.0f}" fill="#ffffff"/>',
         f'<text x="6" y="16" font-size="14" fill="#222">{html.escape(title)}</text>',
         f'<g transform="translate(0,30)"><rect x="0" y="0" width="{W:.1f}" height="{H:.1f}" fill="#f7f7f7" stroke="#888"/>']
    for r in D["rows"]:
        o.append(f'<rect x="{(r["x"]-x0)*S:.1f}" y="{(y1-r["y"]-pdlib.ROW_H)*S:.1f}" '
                 f'width="{r["n"]*r["step"]*S:.1f}" height="{pdlib.ROW_H*S:.1f}" fill="none" stroke="#e8e8e8" stroke-width="0.5"/>')
    REP = ("fanout", "load_slew", "wire", "rebuffer", "split", "hold")
    for n, c in D["comps"].items():
        if c["x"] is None:
            continue
        m = c["master"].replace(pdlib.PFX, "")
        if m.startswith(("fill_", "fillcap", "decap")) or n.startswith("FILLER"):
            continue
        w, h = L[c["master"]]["w"], L[c["master"]]["h"]
        if m.startswith(("filltie", "endcap")):
            col = COL["tap"]
        elif n.startswith(("clkbuf_", "clkload")):
            col = COL["CLKTREE"]
        elif n.startswith(REP):
            col = COL["repair"]
        else:
            col = colour(mod.get(n, "other"))
        o.append(f'<rect x="{(c["x"]-x0)*S:.2f}" y="{(y1-c["y"]-h)*S:.2f}" width="{w*S:.2f}" '
                 f'height="{h*S:.2f}" fill="{col}" stroke="#ffffff" stroke-width="0.3"><title>{html.escape(n)} {m} '
                 f'{html.escape(mod.get(n, ""))}</title></rect>')
    if regions:
        for r in regions["regions"]:
            rx0, ry0, rx1, ry1 = r["rect"]
            o.append(f'<rect x="{(rx0-x0)*S:.1f}" y="{(y1-ry1)*S:.1f}" width="{(rx1-rx0)*S:.1f}" '
                     f'height="{(ry1-ry0)*S:.1f}" fill="none" stroke="#000" stroke-width="2" stroke-dasharray="6,3"/>')
            o.append(f'<text x="{(rx0-x0)*S+4:.1f}" y="{(y1-ry1)*S+14:.1f}" font-size="13" fill="#000">'
                     f'{html.escape(r["name"])}</text>')
    for pn, p in D["pins"].items():
        if p["x"] is None:
            continue
        o.append(f'<rect x="{(p["x"]-x0)*S-2:.1f}" y="{(y1-p["y"])*S-4:.1f}" width="4" height="6" fill="#000"><title>{html.escape(pn)}</title></rect>')
    o.append("</g>")
    lx = 6
    for k in ["FE", "CTRL", "MAC", "EXP", "MAX", "DIV", "shared", "repair", "CLKTREE", "tie", "tap"]:
        o.append(f'<rect x="{lx}" y="{H+40:.0f}" width="12" height="12" fill="{COL[k]}" stroke="#666" stroke-width="0.5"/>'
                 f'<text x="{lx+16}" y="{H+51:.0f}" font-size="12" fill="#222">{k}</text>')
        lx += 16 + 9 * len(k) + 18
    o.append("</svg>")
    open(out, "w").write("\n".join(o))
    print(out)


if __name__ == "__main__":
    main()
