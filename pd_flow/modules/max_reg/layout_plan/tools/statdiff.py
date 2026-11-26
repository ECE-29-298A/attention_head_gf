#!/usr/bin/env python3
"""statdiff.py <base.stat.json> <x.stat.json> ... : chip synthesis area with cells of unknown area
(excluded from synthesis, e.g. sdffq_1) added back from the Liberty, and the per-family cell diff."""
import json, re, sys
LIB = ("/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee/"
       "gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib")
area = {}; cur = None
for line in open(LIB):
    m = re.match(r'\s*cell\s*\(\s*"?gf180mcu_fd_sc_mcu7t5v0__(\w+)"?\s*\)', line)
    if m: cur = m.group(1)
    m = re.match(r'\s*area\s*:\s*([\d.]+)', line)
    if m and cur and cur not in area: area[cur] = float(m.group(1))
def load(fn):
    d = json.load(open(fn)); top = d.get("design") or next(iter(d["modules"].values()))
    cnt = {k.split("__")[-1]: v for k, v in top["num_cells_by_type"].items()}
    tot = sum(area[k] * v for k, v in cnt.items())
    return top["area"], tot, cnt
b = load(sys.argv[1])
print(f"{'run':40s} {'yosys_area':>11s} {'liberty_area':>12s} {'delta':>8s} cells")
for fn in sys.argv[1:]:
    ya, la, cnt = load(fn)
    print(f"{fn.split('/')[-1]:40s} {ya:11.1f} {la:12.1f} {la - b[1]:+8.1f} {sum(cnt.values())}")
    if fn == sys.argv[1]: continue
    fam = lambda k: re.sub(r'_\d+$', '', k)
    df = {}
    for k in set(cnt) | set(b[2]):
        d = cnt.get(k, 0) - b[2].get(k, 0)
        if d: df.setdefault(fam(k), [0, 0.0]); df[fam(k)][0] += d; df[fam(k)][1] += d * area[k]
    print("   by family (count, um2):", ", ".join(f"{k} {v[0]:+d}/{v[1]:+.0f}" for k, v in sorted(df.items(), key=lambda kv: kv[1][1])))
