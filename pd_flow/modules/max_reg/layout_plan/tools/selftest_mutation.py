#!/usr/bin/env python3
"""Adapted from layout_review/selftest_mutation.py (review round 1 N1) for the v2 validator: disable each
targeted check in memory (validator source untouched) and require that its self-test turns BAD while the other
self-tests are unchanged. Writes evidence/selftest_mutation.{log,json}."""
import json, os, sys, types
LP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LP); sys.path.insert(0, LP + "/tools")
SRC = open(LP + "/validate_placement.py").read()
OUT = LP + "/out"
def load(src):
    m = types.ModuleType("vp_mut"); m.__file__ = LP + "/validate_placement.py"
    exec(compile(src, LP + "/validate_placement.py", "exec"), m.__dict__); return m
MUT = {
 "overlap": ('if (rr, k) in occ: E("geometry", f"overlap', 'if False: E("geometry", f"overlap'),
 "off-grid": ('E("geometry", f"{r[\'inst\']} off the site/row grid")', 'None'),
 "orientation vs row parity": ('if r[key] not in (native, G.mirror(native)): E(', 'if False: E('),
 "tap overlap (b_m shifted -4 sites)": ('if as_ < t1 and t0 < as_ + ww: E("tap"', 'if False: E("tap"'),
 "outside rows 1..37 (b_m shifted +16 rows)": ('E("outside_core", f"{r[\'inst\']} outside rows', 'E("geometry", f"{r[\'inst\']} outside rows'),
 "compare chain broken": ('if r0 is None or not (r1 - r0 == 1 or skip):', 'if False:'),
 "chain input moved off A1": ('if z != f"c[{i}]": E("intent"', 'if False: E("intent"'),
 "oai21 gt moved off A1": ('if ld["pins"]["A1"] != "gt":', 'if False:'),
 "slow chain cell (aoi222_1) substituted": ('if _SLEW.get(c["master"], 99) >= limit:', 'if False:'),
 "b_m instance names swapped": ('if t != "dffq_1" or not m or int(m.group(1)) != c["bit"]:', 'if False:'),
 "v1 SE: one driver on 22 SE pins": ('if fo > lim["fanout"]:', 'if False:'),
 "SE driver too weak for its load (fanout legal)": ('if tr >= tmax:', 'if False:'),
}
G = __import__("gen_placement")
cen = G.census(); ctx = G.chip_context()
man = json.load(open(os.path.join(OUT, "MANIFEST.json")))
nl_names = G.parse_netlist(os.path.normpath(os.path.join(LP, man["inputs"]["names_netlist"][0])))
ref = {n: ok for n, ok, f in load(SRC).selftests(OUT, cen, ctx, nl_names)}
lines = [f"unmutated: {ref}"]; res = {}; allgood = all(ref.values())
for case, (old, new) in MUT.items():
    assert SRC.count(old) == 1, (case, SRC.count(old))
    st = {n: (ok, f) for n, ok, f in load(SRC.replace(old, new)).selftests(OUT, cen, ctx, nl_names)}
    others = [n for n in st if n != case and st[n][0] != ref[n]]
    bad = not st[case][0]
    allgood &= bad and not others
    res[case] = {"target_now": "BAD (depends on its check)" if bad else "still ok (NOT dependent)", "fired": st[case][1],
                 "others_changed": others}
    lines.append(f"{case:50s} -> {res[case]['target_now']}  others_changed={others}")
lines.append("ALL_SELFTESTS_DEPEND_ON_THEIR_CHECK" if allgood else "FAILED")
open(LP + "/evidence/selftest_mutation.log", "w").write("\n".join(lines) + "\n")
json.dump(res, open(LP + "/evidence/selftest_mutation.json", "w"), indent=1)
print("\n".join(lines))
