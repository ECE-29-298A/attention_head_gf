#!/usr/bin/env python3
"""Module-level switched-capacitance comparison of fixed-width ripple_add netlists.

Workload: K uniform-random (a, b, cin) vectors applied back to back (seed fixed), i.e. the
neutral stand-in of energy-measurement.md section 3; the real mac_unit stream is not modelled.
Two delay models: zero-delay (functional toggles only: a floor) and synchronous unit-delay
(every cell output one step after its inputs: an indicator of glitching, not a timing model).
Metric per net: toggles x receiver pin capacitance (Liberty TT input caps; output port load
0 here, wire 0: wire share comes from extraction in Phase 4). Internal cell energy is not
counted here (see OpenSTA report_power in sta/). Output: activity.json.
"""
import json, os, random, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from cellfun import load_netlist, Evaluator, liberty

HERE = os.path.dirname(os.path.abspath(__file__))
K = int(os.environ.get("K", "4000")); SEED = 20261126

def vectors(n, k, seed):
    r = random.Random(seed)
    return [(r.getrandbits(n), r.getrandbits(n), r.getrandbits(1)) for _ in range(k)]

def pack(nl, vecs, n):
    """Bit-parallel: bit j of each port bit = vector j."""
    vals = {}
    for name, key in (("a", 0), ("b", 1)):
        for i, bit in enumerate(nl["ports"][name]["bits"]):
            x = 0
            for j, v in enumerate(vecs):
                if (v[key] >> i) & 1: x |= 1 << j
            vals[bit] = x
    x = 0
    for j, v in enumerate(vecs):
        if v[2]: x |= 1 << j
    vals[nl["ports"]["cin"]["bits"][0]] = x
    return vals

def analyse(path, n):
    nl = load_netlist(path)
    ev = Evaluator(nl)
    lib = ev.lib
    vecs = vectors(n, K, SEED)
    M = (1 << K) - 1
    vals = ev.run(pack(nl, vecs, n), M)
    # function check against a+b+cin
    sbits = nl["ports"]["s"]["bits"]
    for j, (a, b, c) in enumerate(vecs):
        got = sum(((vals[bb] >> j) & 1) << i for i, bb in enumerate(sbits))
        assert got == (a + b + c) % (1 << n), (path, j)
    # sink pin cap per net
    sinkcap = {}
    for inst in nl["insts"].values():
        for p, b in inst["conn"].items():
            pd = lib[inst["master"]]["pins"][p]
            if pd["dir"] == "input" and isinstance(b, int):
                sinkcap[b] = sinkcap.get(b, 0.0) + pd["cap_pF"]
    # zero-delay toggles between consecutive vectors
    zd = {b: bin((v ^ (v >> 1)) & ((1 << (K - 1)) - 1)).count("1") for b, v in vals.items()}
    # unit-delay: transitions vector j -> j+1, bit-parallel over the K-1 pairs
    old = {}; new = {}
    for b in pack(nl, vecs, n):
        v = vals[b]
        old[b] = v & ((1 << (K - 1)) - 1); new[b] = (v >> 1) & ((1 << (K - 1)) - 1)
    ud, _, steps = ev.run_unit_delay(old, new, (1 << (K - 1)) - 1)
    nets = set(sinkcap) | set(zd)
    def cls(b):
        nm = nl["names"].get(b, str(b))
        if nm.startswith(("a[", "b[", "cin")): return "inputs"
        if nm.startswith("s["): return "outputs"
        return "internal"
    agg = {}
    for b in nets:
        c = cls(b); g = agg.setdefault(c, {"nets": 0, "zd_toggles": 0, "ud_toggles": 0, "zd_fC_per_vec": 0.0, "ud_fC_per_vec": 0.0})
        g["nets"] += 1; g["zd_toggles"] += zd.get(b, 0); g["ud_toggles"] += ud.get(b, 0)
        g["zd_fC_per_vec"] += zd.get(b, 0) * sinkcap.get(b, 0.0) * 1000 / (K - 1)
        g["ud_fC_per_vec"] += ud.get(b, 0) * sinkcap.get(b, 0.0) * 1000 / (K - 1)
    tot_zd = sum(g["zd_fC_per_vec"] for g in agg.values()); tot_ud = sum(g["ud_fC_per_vec"] for g in agg.values())
    area = sum(lib[i["master"]]["area"] for i in nl["insts"].values())
    pin_total = sum(sinkcap.values()) * 1000
    return {"netlist": os.path.relpath(path, HERE), "N": n, "cells": len(nl["insts"]), "area_um2": round(area, 4),
            "total_receiver_pin_cap_fF": round(pin_total, 2),
            "switched_pin_cap_fF_per_vector_zero_delay": round(tot_zd, 2),
            "switched_pin_cap_fF_per_vector_unit_delay": round(tot_ud, 2),
            "glitch_factor_unit_over_zero": round(tot_ud / tot_zd, 3),
            "unit_delay_settle_steps_max": steps, "by_class": agg, "vectors": K, "seed": SEED,
            "function_check": f"pass ({K} random vectors vs (a+b+cin) mod 2^{n})"}

if __name__ == "__main__":
    out = {}
    for f in sorted(os.listdir(os.path.join(HERE, "netlists"))):
        n = int(f.split("_n")[1].split(".")[0])
        r = analyse(os.path.join(HERE, "netlists", f), n); out[f[:-2]] = r
        print(f"{f[:-2]:14s} cells={r['cells']:3d} area={r['area_um2']:9.2f} pinC={r['total_receiver_pin_cap_fF']:7.1f}fF "
              f"swC/vec zero-delay={r['switched_pin_cap_fF_per_vector_zero_delay']:7.1f}fF unit-delay={r['switched_pin_cap_fF_per_vector_unit_delay']:7.1f}fF "
              f"glitch={r['glitch_factor_unit_over_zero']:.3f}")
    json.dump(out, open(os.path.join(HERE, "activity.json"), "w"), indent=1)
