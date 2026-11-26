#!/usr/bin/env python3
"""Integration evidence check on the chip run layout_plan/chip_runs/fixed_a3 (D3: not shipped).

Usage: check_chip_integration.py OUT.json
I1 the final chip netlist (nl and pnl) contains, for each adder instance (core.mac.adder N=22,
   core.mac.l_adder N=12), exactly the frozen cells: bitslice[i].u_fa = addf_1 (i < N-1) and
   u_msb_x3 = xor3_1, with the carry chain CO(i) -> CI(i+1) and CO(N-2) -> A3 of the MSB, every
   carry net with exactly one driver and one load (no buffer, no resynthesis or resize);
I2 the synthesized netlist (step 06) has the same instances/masters (so Yosys/ABC did not remap);
I3 every one of those instances is FIXED at its ra_fixed.cfg coordinate/orientation in the final DEF.
"""
import gzip
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CR = HERE.parents[1] / "layout_plan" / "chip_runs" / "fixed_a3"
RUN = Path("/Users/samuelzhang/ttharden/ra_fixed_a3/runs/wokwi")
WIDTH = {"core.mac.adder": 22, "core.mac.l_adder": 12}


def insts(text):
    text = re.sub(r"//.*", "", text)
    out = {}
    for m in re.finditer(r"(gf180mcu_fd_sc_mcu7t5v0__\w+)\s+(\\?\S+)\s*\((.*?)\);", text, re.S):
        pins = {p: v.replace("\\", "").replace(" ", "")
                for p, v in re.findall(r"\.(\w+)\s*\(\s*([^()]*?)\s*\)", m.group(3))}
        out[m.group(2).replace("\\", "").strip()] = (m.group(1), pins)
    return out


def check_netlist(text):
    ins = insts(text)
    loads, drivers = {}, {}
    outpins = {"CO", "S", "Z", "ZN", "Q", "QN"}
    for nm, (mst, pins) in ins.items():
        for p, net in pins.items():
            if p in ("VDD", "VSS", "VNW", "VPW"):
                continue
            (drivers if p in outpins else loads).setdefault(net, []).append(f"{nm}.{p}")
    res = {}
    for pre, n in WIDTH.items():
        errs = []
        own = sorted(k for k in ins if k.startswith(pre + "."))
        exp = [f"{pre}.bitslice[{i}].u_fa" for i in range(n - 1)] + [f"{pre}.u_msb_x3"]
        extra = [k for k in own if k not in exp]
        for i in range(n - 1):
            k = f"{pre}.bitslice[{i}].u_fa"
            if k not in ins or ins[k][0] != "gf180mcu_fd_sc_mcu7t5v0__addf_1":
                errs.append(f"{k} missing or wrong master {ins.get(k, ('-',))[0]}")
                continue
            co = ins[k][1]["CO"]
            nxt = (f"{pre}.bitslice[{i+1}].u_fa", "CI") if i < n - 2 else (f"{pre}.u_msb_x3", "A3")
            if nxt[0] not in ins or ins[nxt[0]][1].get(nxt[1]) != co:
                errs.append(f"carry {k}.CO={co} not on {nxt[0]}.{nxt[1]}")
            if loads.get(co) != [f"{nxt[0]}.{nxt[1]}"] or drivers.get(co) != [f"{k}.CO"]:
                errs.append(f"carry net {co}: drivers {drivers.get(co)} loads {loads.get(co)}")
        k = f"{pre}.u_msb_x3"
        if k not in ins or ins[k][0] != "gf180mcu_fd_sc_mcu7t5v0__xor3_1":
            errs.append(f"{k} missing or wrong master")
        res[pre] = {"N": n, "cells_found": len([k for k in exp if k in ins]), "expected": n,
                    "extra_cells_in_namespace": {e: ins[e][0].split("__")[1] for e in extra},
                    "msb_A3_net": ins.get(k, (None, {}))[1].get("A3"), "errors": errs,
                    "pass": not errs}
    return res


def main():
    out = Path(sys.argv[1])
    r = {"run": str(CR), "checks": {}}
    for tag, p in (("I1_final_nl", CR / "harden/nl/tt_um_attention_head_gf.nl.v"),
                   ("I1_final_pnl", CR / "harden/pnl/tt_um_attention_head_gf.pnl.v"),
                   ("I2_synth_nl", RUN / "06-yosys-synthesis/tt_um_attention_head_gf.nl.v")):
        r["checks"][tag] = check_netlist(p.read_text()) if p.exists() else {"missing": str(p)}
    cfg = {}
    for line in (CR / "ra_fixed.cfg").read_text().splitlines():
        if line.strip():
            nm, x, y, o = line.split()
            cfg[nm.replace("\\", "")] = (round(float(x) * 2000), round(float(y) * 2000), o)
    d = (CR / "harden/def/tt_um_attention_head_gf.def").read_text()
    comps = {}
    for m in re.finditer(r"- (\S+) (\S+) \+ (FIXED|PLACED|FIRM)[^(]*\( (-?\d+) (-?\d+) \) (\w+)", d):
        comps[m.group(1).replace("\\", "")] = (m.group(2), m.group(3), int(m.group(4)), int(m.group(5)), m.group(6))
    bad = [(k, comps.get(k)) for k, (x, y, o) in cfg.items()
           if not comps.get(k) or comps[k][1] != "FIXED" or comps[k][2:] != (x, y, o)]
    r["checks"]["I3_def_fixed"] = {"cfg_cells": len(cfg), "bad": bad[:10], "pass": not bad}
    ok = all(v.get("pass", False) for c in r["checks"].values() for v in
             (c.values() if "pass" not in c else [c]) if isinstance(v, dict))
    r["all_pass"] = ok
    out.write_text(json.dumps(r, indent=1) + "\n")
    for k, c in r["checks"].items():
        if "pass" in c:
            print(k, "PASS" if c["pass"] else "FAIL", c.get("cfg_cells"))
        else:
            for pre, v in c.items():
                print(k, pre, "PASS" if v.get("pass") else "FAIL", v.get("cells_found"), v.get("extra_cells_in_namespace"), v.get("errors", [])[:3])
    print("ALL_PASS" if ok else "FAILED")


if __name__ == "__main__":
    main()
