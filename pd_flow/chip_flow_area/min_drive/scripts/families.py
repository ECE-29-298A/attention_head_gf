#!/usr/bin/env python3
"""GF180 7-track cell families, drive variants and LEF areas, and the dont-use lists of the
minimum-drive experiment.

Classes (by family name):
  keep      buf, clkbuf, inv, clkinv (repair / CTS / dummy loads), dly*, fill*, filltie,
            endcap, antenna, hold, tieh, tiel, bufz, invz (tristate, unused)
  logic     every other combinational family (and, or, nand, nor, aoi*, oai*, xor*, xnor*,
            mux2, mux4, addf, addh)
  seq       dff*, sdff*, lat*, icgt* (flops, latches, clock gates)
PDK exclusions (drc_exclude.cells): mux2_1, oai33_2. So the minimum *available* mux2 is mux2_2.
"""
import json
import re
import sys
from collections import defaultdict

PFX = "gf180mcu_fd_sc_mcu7t5v0__"
LEF = ("/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/"
       "54435919abffb937387ec956209f9cf5fd2dfbee/gf180mcuD/libs.ref/"
       "gf180mcu_fd_sc_mcu7t5v0/lef/gf180mcu_fd_sc_mcu7t5v0.lef")
PDK_EXCLUDED = {"mux2_1", "oai33_2"}
KEEP = {"buf", "clkbuf", "inv", "clkinv", "dlya", "dlyb", "dlyc", "dlyd", "fill", "fillcap",
        "filltie", "endcap", "antenna", "hold", "tieh", "tiel", "bufz", "invz"}
SEQ_RX = re.compile(r"^(dff|sdff|lat|icgt)")
H2_EXCLUDED = ["dly*", "buf_1", "clkbuf_1", "buf_2", "clkbuf_2"]


def lef_areas():
    areas, cur = {}, None
    for line in open(LEF):
        m = re.match(r"\s*MACRO\s+(\S+)", line)
        if m:
            cur = m.group(1)[len(PFX):]
            continue
        m = re.match(r"\s*SIZE\s+([\d.]+)\s+BY\s+([\d.]+)", line)
        if m and cur:
            areas[cur] = round(float(m.group(1)) * float(m.group(2)), 4)
    return areas


def families():
    fam = defaultdict(dict)
    for c, a in lef_areas().items():
        m = re.match(r"(.*)_(\d+)$", c)
        if m:
            fam[m.group(1)][int(m.group(2))] = a
    return fam


def cls(f):
    if f in KEEP:
        return "keep"
    return "seq" if SEQ_RX.match(f) else "logic"


def variants(f):
    """(drive, area, name) sorted by drive, PDK-excluded variants removed."""
    return [(d, a, f"{f}_{d}") for d, a in sorted(families()[f].items()) if f"{f}_{d}" not in PDK_EXCLUDED]


def above_min():
    """every logic/seq variant above the smallest available one of its family"""
    out = []
    for f in sorted(families()):
        if cls(f) == "keep":
            continue
        v = variants(f)
        out += [n for d, a, n in v[1:]]
    return out


def drive_at_least(k):
    out = []
    for f in sorted(families()):
        if cls(f) == "keep":
            continue
        v = variants(f)
        out += [n for d, a, n in v[1:] if d >= k]
    return out


def cost_above(limit):
    """variants whose area exceeds the family's smallest available variant by more than limit"""
    out = []
    for f in sorted(families()):
        if cls(f) == "keep":
            continue
        v = variants(f)
        a0 = v[0][1]
        out += [n for d, a, n in v[1:] if a - a0 > limit + 1e-6]
    return out


def full(names):
    return [PFX + n for n in names]


if __name__ == "__main__":
    a = lef_areas()
    print("buf_3 area", a["buf_3"])
    for name, lst in [("above_min", above_min()), ("drive>=4", drive_at_least(4)),
                      ("cost>buf_3", cost_above(a["buf_3"]))]:
        print(name, len(lst), lst if "-v" in sys.argv else "")
