#!/usr/bin/env python3
"""Validator for the ripple_add tetris placement (experiments.md section 5 checklist).

  1 stale      regenerate every view in memory (gen_placement.generate) and diff against out/
  2 views      netlist (Yosys flatten), CSV, JSON, chip-anchor JSON and CFG agree on instance,
               master, position and orientation
  3 geometry   cell count and site-row checksum; on the site/row grid; inside the footprint;
               no overlap within a row; orientation legal for the row parity
  4 intent     bit i in relative row i; carry cells share one column; every carry hop spans
               exactly one row; the MSB pin assignment in the netlist equals the placement record
  5 connect    one driver per non-input net, a sink for every non-output net, boundary pins
  6 function   emitted netlist evaluated cell by cell from Liberty functions: N=12 exhaustive
               (2^25), N=22 random 2^20 + carry-chain patterns; carry bus c[i] checked too;
               reference is numpy integer addition (independent of the netlist)
  7 library    master sizes in the LEF equal the generator's width table; LEF hash logged
  8 pins       every signal pin has an on-grid Via1 access point whose M2 pad lies inside the
               cell outline (cannot be blocked by an abutting neighbour); chip anchor clear of
               FIXED taps/endcaps (hard) and Metal4 stripes (soft)
  9 self-test  deliberately illegal inputs must be rejected
Usage: validate_placement.py [--out DIR] [--skip-function] -> writes DIR/validation.json
"""
import argparse, copy, csv, io, json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "tools"))
import gen_placement as G  # noqa: E402
import lefcensus  # noqa: E402
from cellfun import load_netlist, Evaluator  # noqa: E402

P = G.P


def load_bundle(out):
    return {f: open(os.path.join(out, f)).read() for f in sorted(os.listdir(out))
            if os.path.isfile(os.path.join(out, f)) and f != "validation.json"}


def check(bundle, n, cen, ctx, nl, errors, notes):
    E = lambda m: errors.append(f"N={n}: {m}")
    info = json.loads(bundle[f"placement_n{n}.json"])
    rows = list(csv.DictReader(io.StringIO(bundle[f"placement_n{n}.csv"])))
    mgp = json.loads(bundle[f"chip_anchor_n{n}.json"])["placement"]
    cfg = [l.split() for l in bundle[f"chip_anchor_n{n}.cfg"].splitlines() if l.strip()]
    anc = info["default_chip_anchor"]; r0, s0 = anc["row"], anc["site"]; path = anc["inst_path"]
    W, H = info["footprint"]["width_sites"], info["footprint"]["height_rows"]
    # ---- 2 views agree
    ni = {k: v["master"] for k, v in nl["insts"].items()}
    ci = {r["inst"]: r["master"] for r in rows}
    ji = {c["inst"]: c["master"] for c in info["cells"]}
    if ni != ci: E(f"netlist vs CSV instances/masters differ: {sorted(set(ni.items()) ^ set(ci.items()))[:4]}")
    if ci != ji: E("CSV vs JSON instances/masters differ")
    if set(mgp) != {f"{path}.{k}" for k in ci}: E("chip-anchor JSON instance names differ from netlist")
    if {l[0] for l in cfg} != set(mgp): E("CFG and JSON chip anchors differ")
    for l in cfg:
        name, x, y, o = l[0], float(l[1]), float(l[2]), l[3]
        m = mgp.get(name)
        if m and (abs(m["location"][0] - x) > 1e-6 or abs(m["location"][1] - y) > 1e-6 or m["orientation"] != o):
            E(f"CFG/JSON disagree for {name}")
    for r, c in zip(rows, info["cells"]):
        for k in ("rel_row", "rel_site", "width_sites"):
            if int(r[k]) != c[k]: E(f"CSV/JSON {k} differ for {r['inst']}")
        if r["orient_even_anchor"] != c["orient_even_anchor"] or r["orient_odd_anchor"] != c["orient_odd_anchor"]:
            E(f"CSV/JSON orientation differ for {r['inst']}")
    # ---- 3 geometry
    if len(rows) != n: E(f"cell count {len(rows)} != {n}")
    sr = sum(int(r["width_sites"]) for r in rows)
    if sr != info["footprint"]["site_rows_used"]: E("site-row checksum mismatch")
    occ = {}
    for r in rows:
        rr, ss, ww = int(r["rel_row"]), int(r["rel_site"]), int(r["width_sites"])
        m = r["master"]
        lefw = cen["masters"][m]["sites"]
        if ww != lefw: E(f"{r['inst']}: width table {ww} != LEF {lefw} sites")
        if abs(float(r["rel_x_um"]) - ss * G.SITE_W) > 1e-6 or abs(float(r["rel_y_um"]) - rr * G.ROW_H) > 1e-6:
            E(f"{r['inst']}: um coordinates not on the site/row grid")
        if not (0 <= rr < H and 0 <= ss and ss + ww <= W): E(f"{r['inst']}: outside footprint")
        for k in range(ss, ss + ww):
            if (rr, k) in occ: E(f"overlap at row {rr} site {k}: {occ[(rr, k)]} / {r['inst']}")
            occ[(rr, k)] = r["inst"]
        sym = cen["masters"][m]["symmetry"]
        for par, key in ((0, "orient_even_anchor"), (1, "orient_odd_anchor")):
            native = G.row_orient(par + rr)
            o = r[key]
            if o not in (native, G.mirror(native)): E(f"{r['inst']}: orientation {o} illegal in a {native} row")
            if o != native and "Y" not in sym: E(f"{r['inst']}: mirror needs SYMMETRY Y")
    # anchored absolute coordinates
    for c in info["cells"]:
        name = f"{path}.{c['inst']}"
        x, y = mgp[name]["location"]; o = mgp[name]["orientation"]
        ex = G.CORE_X0 + (s0 + c["rel_site"]) * G.SITE_W; ey = G.CORE_Y0 + (r0 + c["rel_row"]) * G.ROW_H
        if abs(x - ex) > 1e-6 or abs(y - ey) > 1e-6: E(f"{name}: anchored location off grid/anchor")
        if abs(round(x * 2000) - x * 2000) > 1e-6 or abs(round(y * 2000) - y * 2000) > 1e-6: E(f"{name}: not on 0.5 nm DBU")
        par = (r0 + c["rel_row"]) % 2
        want = c["orient_even_anchor"] if r0 % 2 == 0 else c["orient_odd_anchor"]
        if o != want: E(f"{name}: anchored orientation {o} != {want}")
        if G.row_orient(r0 + c["rel_row"]) not in (o, G.mirror(o)): E(f"{name}: orientation vs chip row")
    # ---- 4 intent
    byb = {c["bit"]: c for c in info["cells"]}
    for i in range(n):
        c = byb[i]
        if c["rel_row"] != i: E(f"bit {i} not in relative row {i}")
        if i < n - 1 and (c["master"] != P + "addf_1" or c["rel_site"] != 0): E(f"bit {i} not an addf_1 at site 0")
    if byb[n - 1]["master"] != P + "xor3_1": E("MSB is not xor3_1")
    # netlist carry chain + MSB pins
    names = nl["names"]
    def net(inst, pin):
        b = nl["insts"][inst]["conn"].get(pin)
        return names.get(b, b) if isinstance(b, int) else b
    for i in range(n - 1):
        inst = f"bitslice[{i}].u_fa"
        if net(inst, "A") != f"a[{i}]" or net(inst, "B") != f"b[{i}]" or net(inst, "S") != f"s[{i}]":
            E(f"{inst}: data pins not on a[{i}]/b[{i}]/s[{i}]")
        exp_ci = "cin" if i == 0 else f"c[{i}]"
        if i == 0:
            if nl["insts"][inst]["conn"]["CI"] != nl["ports"]["cin"]["bits"][0]: E("bit 0 CI not on cin")
        elif nl["insts"][inst]["conn"]["CI"] != nl["insts"][f"bitslice[{i-1}].u_fa"]["conn"]["CO"]:
            E(f"carry {i-1}->{i} not CO->CI")
        if i > 0 and abs(byb[i]["rel_row"] - byb[i - 1]["rel_row"]) != 1: E(f"carry hop {i-1}->{i} spans != 1 row")
    msb = byb[n - 1]["pins"]
    want = {msb["a"]: nl["ports"]["a"]["bits"][n - 1], msb["b"]: nl["ports"]["b"]["bits"][n - 1],
            msb["c_in"]: nl["insts"][f"bitslice[{n-2}].u_fa"]["conn"]["CO"]}
    for pin, bit in want.items():
        if nl["insts"]["u_msb_x3"]["conn"][pin] != bit: E(f"u_msb_x3.{pin} does not match the placement pin record")
    if nl["insts"]["u_msb_x3"]["conn"]["Z"] != nl["ports"]["s"]["bits"][n - 1]: E("u_msb_x3.Z not on s[N-1]")
    # ---- 5 connectivity
    lib = Evaluator(nl).lib
    drivers, sinks = {}, {}
    for iname, inst in nl["insts"].items():
        for p, b in inst["conn"].items():
            d = lib[inst["master"]]["pins"][p]["dir"]
            if d == "output": drivers.setdefault(b, []).append(iname)
            else: sinks.setdefault(b, []).append(iname)
    pin_in = {b for k, p in nl["ports"].items() if p["dir"] == "input" for b in p["bits"]}
    pin_out = {b for k, p in nl["ports"].items() if p["dir"] == "output" for b in p["bits"]}
    for b in set(drivers) | set(sinks) | pin_out:
        nd = len(drivers.get(b, [])) + (1 if b in pin_in else 0)
        if nd != 1: E(f"net {names.get(b, b)} has {nd} drivers")
        if b not in pin_out and not sinks.get(b) and b not in pin_in:
            E(f"net {names.get(b, b)} has no sink")
    dangling = [i for i, inst in nl["insts"].items() for p, b in inst["conn"].items() if not isinstance(b, int)]
    if dangling: E(f"constant/unconnected pins: {dangling[:4]}")
    if len(pin_in) != 2 * n + 1 or len(pin_out) != n: E(f"boundary pins {len(pin_in)} in / {len(pin_out)} out")
    unused_in = [names.get(b) for b in pin_in if b not in sinks]
    if unused_in: E(f"unused inputs {unused_in}")
    # ---- 8 pins / access
    for c in info["cells"]:
        m = cen["masters"][c["master"]]
        for net_, pin in c["pins"].items():
            p = m["pins"][pin]
            if p["n_access"] < 1: E(f"{c['inst']}.{pin}: no on-grid Via1 access point"); continue
            ok = [x for x in p["access_x_N"] if 0.14 - 1e-6 <= x - 0.14 and x + 0.14 <= m["width_um"] - 0.0 + 1e-6
                  and x - 0.14 >= 0.0 - 1e-6]
            if not ok: E(f"{c['inst']}.{pin}: every access pad leaves the outline")
            for x in p["access_x_N"]:
                k = (x - 0.28) / 0.56
                if abs(k - round(k)) > 1e-6: E(f"{c['inst']}.{pin}: access x {x} off the M2 track grid")
    hard, soft = G.anchor_checks([{"inst": c["inst"], "master": c["master"].replace(P, ""), "rel_row": c["rel_row"],
                                   "rel_site": c["rel_site"]} for c in info["cells"]], cen, ctx, (r0, s0))
    for h in hard: E(f"anchor: {h}")
    notes.append(f"N={n}: anchor (row {r0}, site {s0}) soft warnings: {soft or 'none'}")
    return info


def function_check(nl, n, errors, notes):
    ev = Evaluator(nl)
    if n <= 12:
        K = 1 << (2 * n + 1)
        idx = np.arange(K, dtype=np.int64)
        a = idx & ((1 << n) - 1); b = (idx >> n) & ((1 << n) - 1); cin = (idx >> (2 * n)) & 1
        mode = f"exhaustive 2^{2*n+1}"
    else:
        rng = np.random.default_rng(20261126)
        K0 = 1 << 20
        a = rng.integers(0, 1 << n, K0, dtype=np.int64); b = rng.integers(0, 1 << n, K0, dtype=np.int64)
        cin = rng.integers(0, 2, K0, dtype=np.int64)
        # carry-chain patterns: full propagate with generate at every position, both cin
        pa, pb, pc = [], [], []
        full = (1 << n) - 1
        for k in range(n):
            for c in (0, 1):
                pa += [full ^ (1 << k), full, 0, 1 << k]; pb += [1 << k, 0, full, full]; pc += [c, c, c, c]
        a = np.concatenate([a, np.array(pa, dtype=np.int64)]); b = np.concatenate([b, np.array(pb, dtype=np.int64)])
        cin = np.concatenate([cin, np.array(pc, dtype=np.int64)])
        K = len(a); mode = f"random 2^20 (seed 20261126) + {len(pa)} carry-chain patterns"
    def tobig(bits_arr):
        return int.from_bytes(np.packbits(bits_arr.astype(np.uint8), bitorder="little").tobytes(), "little")
    vals = {}
    for i, bit in enumerate(nl["ports"]["a"]["bits"]): vals[bit] = tobig((a >> i) & 1)
    for i, bit in enumerate(nl["ports"]["b"]["bits"]): vals[bit] = tobig((b >> i) & 1)
    vals[nl["ports"]["cin"]["bits"][0]] = tobig(cin)
    M = (1 << K) - 1
    out = ev.run(vals, M)
    s = (a + b + cin) & ((1 << n) - 1)
    bad = 0
    for i, bit in enumerate(nl["ports"]["s"]["bits"]):
        if out[bit] != tobig((s >> i) & 1): bad += 1; errors.append(f"N={n}: s[{i}] mismatch ({mode})")
    # intermediate carry bus: carry into bit i = ((a mod 2^i) + (b mod 2^i) + cin) >> i
    for i in range(1, n):
        co = nl["insts"][f"bitslice[{i-1}].u_fa"]["conn"]["CO"]
        m = (1 << i) - 1
        ref = (((a & m) + (b & m) + cin) >> i) & 1
        if out[co] != tobig(ref): bad += 1; errors.append(f"N={n}: carry c[{i}] mismatch")
    notes.append(f"N={n}: function {mode}: {K} vectors, outputs + carry bus, mismatching buses {bad}")


def validate(bundle, cen, ctx, nls, do_function=True):
    errors, notes = [], []
    for n in (22, 12):
        check(bundle, n, cen, ctx, nls[n], errors, notes)
        if do_function:
            function_check(nls[n], n, errors, notes)
    return errors, notes


def netlists_from_bundle(bundle, tmpdir):
    nls = {}
    for n in (22, 12):
        p = os.path.join(tmpdir, f"ripple_add_n{n}.v")
        open(p, "w").write(bundle[f"ripple_add_n{n}.v"])
        nls[n] = load_netlist(p)
    return nls


def self_test(bundle, cen, ctx, nls):
    """Each mutation must produce at least one error."""
    import tempfile
    res = []
    def mut(n, fn, anchor=None):
        """Apply the same edit to the CSV and the JSON view (and re-derive the chip-anchor views),
        so that the geometric check itself, not a view mismatch, has to catch it."""
        b = copy.deepcopy(bundle)
        j = json.loads(b[f"placement_n{n}.json"])
        rows = list(csv.DictReader(io.StringIO(b[f"placement_n{n}.csv"])))
        fn(rows, j["cells"])
        if anchor:
            j["default_chip_anchor"]["row"], j["default_chip_anchor"]["site"] = anchor
        cells = [{"inst": c["inst"], "master": c["master"].replace(P, ""), "rel_row": c["rel_row"],
                  "rel_site": c["rel_site"], "mirror": c["orient_even_anchor"] not in ("N",)} for c in j["cells"]]
        r0, s0 = j["default_chip_anchor"]["row"], j["default_chip_anchor"]["site"]
        mgp, cfg = {}, []
        for c, jc in zip(cells, j["cells"]):
            o = jc["orient_even_anchor"] if r0 % 2 == 0 else jc["orient_odd_anchor"]
            x = round(G.CORE_X0 + (s0 + c["rel_site"]) * G.SITE_W, 3); y = round(G.CORE_Y0 + (r0 + c["rel_row"]) * G.ROW_H, 3)
            name = f"{j['default_chip_anchor']['inst_path']}.{c['inst']}"
            mgp[name] = {"location": [x, y], "orientation": o}; cfg.append(f"{name} {x:.2f} {y:.2f} {o}")
        b[f"chip_anchor_n{n}.json"] = json.dumps({"placement": mgp})
        b[f"chip_anchor_n{n}.cfg"] = "\n".join(cfg) + "\n"
        b[f"placement_n{n}.json"] = json.dumps(j)
        f = io.StringIO(); w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader(); w.writerows(rows); b[f"placement_n{n}.csv"] = f.getvalue(); return b
    def overlap(rows, js):
        rows[1]["rel_row"] = rows[0]["rel_row"]; js[1]["rel_row"] = js[0]["rel_row"]
        rows[1]["rel_y_um"] = rows[0]["rel_y_um"]; js[1]["rel_y_um"] = js[0]["rel_y_um"]
    def offgrid(rows, js):
        rows[2]["rel_x_um"] = str(float(rows[2]["rel_x_um"]) + 0.28)
    def badwidth(rows, js):
        rows[3]["width_sites"] = "32"; js[3]["width_sites"] = 32
    def badorient(rows, js):
        o = "FS" if rows[4]["orient_even_anchor"] == "N" else "N"
        rows[4]["orient_even_anchor"] = o; js[4]["orient_even_anchor"] = o
        o = "N" if rows[4]["orient_odd_anchor"] == "FS" else "FS"
        rows[4]["orient_odd_anchor"] = o; js[4]["orient_odd_anchor"] = o
    def nothing(rows, js):
        pass
    # (name, mutated bundle, substring the INTENDED check's error must contain). A case passes only if
    # that specific check fires; being rejected by some other check does not count.
    cases = [("overlap", mut(22, overlap), "overlap at row"),
             ("off-grid", mut(22, offgrid), "not on the site/row grid"),
             ("wrong master width", mut(12, badwidth), "width table"),
             ("orientation vs row parity", mut(22, badorient), "illegal in a"),
             ("anchor on a FIXED tap (site 35 = row-1 tap at 22.96 um)", mut(22, nothing, anchor=(2, 35)), "overlaps FIXED tap"),
             # east of the core in rows 1-12: no tap row is touched, so only the outside-core check can fire
             ("anchor outside core (site 590, past the 607-site row)", mut(12, nothing, anchor=(1, 590)), "outside core")]
    b = copy.deepcopy(bundle)
    b["ripple_add_n22.v"] = b["ripple_add_n22.v"].replace(".CI(c[i])", ".CI(c[0])")
    cases.append(("broken carry chain (netlist)", b, "not CO->CI"))
    b = copy.deepcopy(bundle)
    src = b["ripple_add_n12.v"]; assert ".A3(c[11])" in src, "self-test expects the carry on A3"
    b["ripple_add_n12.v"] = src.replace(".A3(c[11])", ".A3(a[11])")
    cases.append(("MSB carry moved off A3 (wrong operand on A3)", b, "does not match the placement pin record"))
    with tempfile.TemporaryDirectory() as td:
        for name, bb, want in cases:
            try:
                nls2 = netlists_from_bundle(bb, td) if bb.get("ripple_add_n22.v") != bundle["ripple_add_n22.v"] or bb.get("ripple_add_n12.v") != bundle["ripple_add_n12.v"] else nls
                errs, _ = validate(bb, cen, ctx, nls2, do_function=(nls2 is not nls))
            except Exception as e:  # a crash on illegal input also counts as rejection, but say so
                errs = [f"exception: {type(e).__name__}: {e}"]
            hit = [e for e in errs if want in e]
            res.append({"case": name, "rejected": bool(hit), "intended_check": want,
                        "first_error": (hit or errs or [None])[0], "n_errors": len(errs)})
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    ap.add_argument("--skip-function", action="store_true")
    a = ap.parse_args()
    report = {"checks": {}}
    # 1 stale
    gen = G.generate({"anchor22": G.DEFAULT_ANCHOR[22], "anchor12": G.DEFAULT_ANCHOR[12]})
    bundle = load_bundle(a.out)
    stale = [k for k in gen if bundle.get(k) != gen[k]] + [k for k in bundle if k not in gen]
    report["checks"]["1_stale"] = {"ok": not stale, "stale_files": stale}
    # 7 library
    cen = lefcensus.census(["addf_1", "xor3_1", "filltie", "endcap", "fill_1", "fill_2"])
    ctx = G.chip_context()
    report["library"] = {"cell_lef_sha256": cen["sources"]["cell_lef_sha256"], "tech_lef_sha256": cen["sources"]["tech_lef_sha256"],
                         "site": cen["site"], "widths_sites": {m: e["sites"] for m, e in cen["masters"].items()}}
    nls = {n: load_netlist(os.path.join(a.out, f"ripple_add_n{n}.v")) for n in (22, 12)}
    errors, notes = validate(bundle, cen, ctx, nls, do_function=not a.skip_function)
    report["checks"]["2-8"] = {"ok": not errors, "errors": errors, "notes": notes}
    st = self_test(bundle, cen, ctx, nls)
    report["checks"]["9_self_test"] = {"ok": all(r["rejected"] for r in st), "cases": st}
    report["all_ok"] = all(c["ok"] for c in report["checks"].values())
    json.dump(report, open(os.path.join(a.out, "validation.json"), "w"), indent=1)
    print(json.dumps({k: (v["ok"] if isinstance(v, dict) and "ok" in v else v) for k, v in report["checks"].items()}))
    for n_ in notes: print(" ", n_)
    for e in errors: print("  ERROR", e)
    for r in st: print("  self-test", r["case"], "rejected" if r["rejected"] else "NOT REJECTED", "|", r["first_error"])
    print("ALL_OK" if report["all_ok"] else "FAILED")
    sys.exit(0 if report["all_ok"] else 1)


if __name__ == "__main__":
    main()
