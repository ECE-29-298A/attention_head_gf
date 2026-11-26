#!/usr/bin/env python3
"""region_density.py <out.json> <regions.json> <label>=<def> ... -- measured D8 density per floorplan region
in a DEF: (area of every placed instance except fill/fillcap, clipped to the region, taps/endcaps included)
/ region area; also the CTS cells (clkbuf_*/clkload*) and flow-added cells inside each region."""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(__file__))
import pdlib
L = pdlib.lef_macros()
regs = json.load(open(sys.argv[2]))["regions"]
out = {}
for spec in sys.argv[3:]:
    lab, d = spec.split("=", 1)
    D = pdlib.parse_def(d, want_routes=False)
    res = {}
    for r in regs:
        x0, y0, x1, y1 = r["rect"]
        a = (x1 - x0) * (y1 - y0)
        used = cts = 0.0
        for n, c in D["comps"].items():
            m = c["master"]
            if c["x"] is None or re.search(r"__(fill_\d+|fillcap_\d+)$", m):
                continue
            w, h = L[m]["w"], L[m]["h"]
            ox = max(0.0, min(x1, c["x"] + w) - max(x0, c["x"]))
            oy = max(0.0, min(y1, c["y"] + h) - max(y0, c["y"]))
            used += ox * oy
            if re.match(r"^(clkbuf_|clkload)", n):
                cts += ox * oy
        res[r["name"]] = {"d8": round(used / a, 4), "cell_area": round(used, 1), "cts_area": round(cts, 1), "area": round(a, 1)}
    out[lab] = res
json.dump(out, open(sys.argv[1], "w"), indent=1)
names = [r["name"] for r in regs]
print("region".ljust(10), " ".join(l.rjust(16) for l in out))
for n in names:
    print(n.ljust(10), " ".join(f"{out[l][n]['d8']:.3f} (cts {out[l][n]['cts_area']:.0f})".rjust(16) for l in out))
