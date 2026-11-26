#!/usr/bin/env python3
"""Per-module GF180 mapped-area measurement under one fixed recipe.

Recipe (identical for every candidate, so numbers are comparable):
  Yosys (native, /opt/homebrew/bin/yosys), read sources, chparam as instantiated,
  synth -flatten -top <m>, dfflibmap + abc -liberty (7-track TT 025C 3V30),
  opt_clean, stat -liberty.  ABC script is Yosys's default for abc -liberty.

Usage:
  synth_area.py [--rtl DIR] [--out JSON] [module ...]
Modules default to every module in the shipped hierarchy.
"""
import argparse, json, os, re, subprocess, sys, tempfile, time

PDK = ("/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/"
       "54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD")
LIB = PDK + "/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib"
ALL = ["project.v", "attention_controller.sv", "mac_unit.v", "ripple_add.v",
       "max_reg.v", "exp_lut.v", "divider.v"]

# name -> (top module, parameter overrides as instantiated in the chip)
TARGETS = {
    "ripple_add_22": ("ripple_add", {"N": 22}),
    "ripple_add_12": ("ripple_add", {"N": 12}),
    "max_reg": ("max_reg", {}),
    "exp_lut": ("exp_lut", {"REGISTERED": 0}),
    "divider": ("divider", {"LATCH_DENOMINATOR": 0, "CHECK_INVALID": 0}),
    "mac_unit": ("mac_unit", {"OUTPUTS": 8}),
    "attention_controller": ("attention_controller", {"OUTPUTS": 8}),
    "tt_um_attention_head_gf": ("tt_um_attention_head_gf", {"OUTPUTS": 8}),
}


def run(name, rtl):
    top, params = TARGETS[name]
    srcs = " ".join('"%s"' % os.path.join(rtl, f) for f in ALL)
    chp = "".join(f"chparam -set {k} {v} {top}\n" for k, v in params.items())
    script = f"""
read_liberty -lib {LIB}
read_verilog -sv {srcs}
{chp}hierarchy -check -top {top}
synth -flatten -top {top}
dfflibmap -liberty {LIB}
abc -liberty {LIB}
opt_clean -purge
check -assert
tee -o {{STAT}} stat -liberty {LIB}
"""
    with tempfile.TemporaryDirectory() as d:
        stat = os.path.join(d, "stat.txt")
        ys = os.path.join(d, "s.ys")
        open(ys, "w").write(script.replace("{STAT}", stat))
        t = time.time()
        p = subprocess.run(["/opt/homebrew/bin/yosys", "-q", "-s", ys],
                           capture_output=True, text=True)
        if p.returncode:
            sys.exit(f"{name}: yosys failed\n{p.stdout[-3000:]}{p.stderr[-3000:]}")
        txt = open(stat).read()
    area = float(re.search(r"Chip area for (?:top )?module.*?:\s*([\d.]+)", txt).group(1))
    cells = {}
    for m in re.finditer(r"^\s+(\d+)\s+[\d.E+-]+\s+(gf180mcu_fd_sc_mcu7t5v0__\w+)", txt, re.M):
        cells[m.group(2).split("__")[1]] = int(m.group(1))
    if not cells:  # older stat layout: "cellname  count"
        for m in re.finditer(r"^\s+(gf180mcu_fd_sc_mcu7t5v0__\w+)\s+(\d+)", txt, re.M):
            cells[m.group(1).split("__")[1]] = int(m.group(2))
    flops = sum(v for k, v in cells.items() if k.startswith(("dff", "sdff", "latq", "icgt")))
    return {"module": name, "top": top, "params": params, "area_um2": area,
            "cells": sum(cells.values()), "flops": flops, "cell_counts": cells,
            "seconds": round(time.time() - t, 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rtl", default=os.path.join(os.path.dirname(__file__), "../../src"))
    ap.add_argument("--out")
    ap.add_argument("modules", nargs="*")
    a = ap.parse_args()
    res = [run(m, os.path.abspath(a.rtl)) for m in (a.modules or TARGETS)]
    for r in res:
        print(f"{r['module']:26s} {r['area_um2']:12.4f} um2  cells {r['cells']:5d}  flops {r['flops']:4d}")
    if a.out:
        json.dump({"recipe": "yosys synth -flatten; dfflibmap; abc -liberty; 7t TT 025C 3v30",
                   "yosys": subprocess.run(["/opt/homebrew/bin/yosys", "-V"], capture_output=True,
                                           text=True).stdout.strip(),
                   "liberty": LIB, "results": res}, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
