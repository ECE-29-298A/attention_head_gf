#!/usr/bin/env python3
"""check_held.py <pilot_dir> <run_dir> <out.json>

For every step DEF of a LibreLane run (ManualMacroPlacement onward) assert that each instance of
<pilot_dir>/placement.cfg is present, FIXED, at the exact configured coordinates and orientation,
with the master given in <pilot_dir>/pilot.v (no in-place resize). Tie cells are reported apart:
repair_tie_fanout (RepairDesignPostGPL) deletes and re-creates them by design.
Also classifies every instance the flow added (CTS, ties, repair/hold buffers, diodes, fill).
"""
import glob, json, os, re, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(__file__))
import pdlib


def main(pdir, run, out):
    cfg = {}
    for line in open(os.path.join(pdir, "placement.cfg")):
        t = line.split()
        if t:
            cfg[t[0]] = (round(float(t[1]), 3), round(float(t[2]), 3), t[3])
    masters = dict((n.replace("\\", ""), m) for m, n in
                   re.findall(r"^\s*(gf180mcu_fd_sc_mcu7t5v0__\w+)\s+(\S+)\s*\(", open(os.path.join(pdir, "pilot.v")).read(), re.M))
    ties = {n for n, m in masters.items() if re.search(r"__tie[hl]$", m)}
    res = {"pilot_dir": pdir, "run": run, "configured": len(cfg), "ties_in_cfg": len(ties), "steps": {}}
    defs = sorted(glob.glob(os.path.join(run, "*", "*.def")), key=lambda p: int(os.path.basename(os.path.dirname(p)).split("-")[0]))
    defs += glob.glob(os.path.join(run, "final", "def", "*.def"))
    all_ok = True
    for d in defs:
        step = os.path.basename(os.path.dirname(d)) if "/final/" not in d else "final"
        n = int(step.split("-")[0]) if step != "final" else 999
        if n < 17:
            continue
        D = pdlib.parse_def(d, want_routes=False)
        c = D["comps"]
        bad = Counter()
        examples = []
        for nm, (x, y, o) in cfg.items():
            if nm in ties:
                continue
            k = c.get(nm)
            why = None
            if k is None:
                why = "missing"
            elif k["status"] != "FIXED":
                why = "status " + k["status"]
            elif (round(k["x"], 3), round(k["y"], 3)) != (x, y):
                why = "moved"
            elif k["orient"] != o:
                why = "orient"
            elif k["master"] != masters[nm]:
                why = "resized"
            if why:
                bad[why] += 1
                if len(examples) < 8:
                    examples.append((nm, why, k and (k["master"].replace(pdlib.PFX, ""), k["x"], k["y"], k["orient"])))
        ties_kept = sum(1 for t in ties if t in c)
        added = Counter()
        for nm, k in c.items():
            if nm in cfg:
                continue
            mm = k["master"].replace(pdlib.PFX, "")
            if mm in ("filltie", "endcap"):
                added["tap/endcap"] += 1
            elif mm.startswith(("fill_", "fillcap")):
                added["fill"] += 1
            elif nm.startswith(("clkbuf_", "clkload")):
                added["cts"] += 1
            elif mm.startswith(("tieh", "tiel")):
                added["tie"] += 1
            elif mm.startswith("antenna"):
                added["diode"] += 1
            elif re.match(r"^(hold|rebuffer|split|fanout|load_slew|wire|max_cap|max_length)\d+", nm):
                added["buffer:" + re.match(r"^[a-z_]+", nm).group(0)] += 1
            else:
                added["other:" + mm] += 1
        ok = not bad
        all_ok &= ok
        res["steps"][step] = {"held_exact": len(cfg) - len(ties) - sum(bad.values()), "of": len(cfg) - len(ties),
                              "violations": dict(bad), "examples": examples, "orig_ties_present": ties_kept,
                              "added": dict(added), "ok": ok}
        print(f"{step:42s} held {res['steps'][step]['held_exact']}/{len(cfg)-len(ties)} "
              f"{'OK' if ok else dict(bad)} orig_ties {ties_kept} added {dict(added)}")
    res["ALL_HELD"] = all_ok
    json.dump(res, open(out, "w"), indent=1)
    print("ALL_HELD" if all_ok else "NOT_HELD")


if __name__ == "__main__":
    main(*sys.argv[1:4])
