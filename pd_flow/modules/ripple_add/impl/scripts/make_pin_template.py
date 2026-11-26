#!/usr/bin/env python3
"""Row-aligned pin template (FP_DEF_TEMPLATE) for the standalone ripple_add block.

Usage: make_pin_template.py N OUT.def

Sides and order come from the approved layout_plan/out/block_n<N>_pins.cfg (W: a[i], s[i]
interleaved bottom to top; E: b[i]; S: cin). LibreLane's CustomIOPlacement only spreads pins evenly
and centres them (run impl n22 #1: a[0] at y = 22.68 um, four rows above bit 0), which breaks the
plan's "one row per bit" composition contract (PLAN.md section 5.5). This template puts every pin of
bit i inside relative row i, on a routing track:
  row i spans y = core_y0 + 3.92 i ... + 3.92;  M3 tracks y = 0.28 + 0.56 k.
  a[i]: row bottom + 0.84 (track), s[i]: + 3.08, b[i]: + 1.96. cin: M2 track x = 17.64 (above the
  bit-0 CI access tracks, cell x 12.60-13.72 + 4.48).
Pin shapes copy LibreLane's own (IO_PIN_*_LENGTH 2 um, thickness 2 x min width = 0.56 um).
"""
import json

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLAN_OUT = HERE.parents[1] / "layout_plan" / "out"
DBU = 2000
ROW_H = 3.92
H_LEN, W = 2.0, 0.56


def um(x):
    v = round(x * DBU)
    assert v % 10 == 0, x          # 0.005 um manufacturing grid
    return v


def main():
    n, out = int(sys.argv[1]), Path(sys.argv[2])
    blk = json.loads((PLAN_OUT / f"block_n{n}.json").read_text())
    die = blk["DIE_AREA"]
    core = blk["CORE_AREA"]
    sides, side = {}, None
    for line in (PLAN_OUT / f"block_n{n}_pins.cfg").read_text().split():
        if line.startswith("#"):
            side = line[1:]
            sides[side] = []
        else:
            sides[side].append(line.replace("\\", ""))
    assert sides["S"] == ["cin"], sides["S"]
    assert sides["W"] == [p for i in range(n) for p in (f"a[{i}]", f"s[{i}]")], "W order"
    assert sides["E"] == [f"b[{i}]" for i in range(n)], "E order"
    pins = []  # name, dir, layer, x, y (centre), (half w, half h)
    for i in range(n):
        y0 = core[1] + ROW_H * i
        for name, dy, xc in ((f"a[{i}]", 0.84, die[0] + H_LEN / 2),
                             (f"s[{i}]", 3.08, die[0] + H_LEN / 2),
                             (f"b[{i}]", 1.96, die[2] - H_LEN / 2)):
            y = y0 + dy
            assert abs(((y - 0.28) / 0.56) - round((y - 0.28) / 0.56)) < 1e-9, (name, y)
            d = "OUTPUT" if name.startswith("s") else "INPUT"
            pins.append((name, d, "Metal3", xc, y, H_LEN / 2, W / 2))
    x = 17.64
    assert abs(((x - 0.28) / 0.56) - round((x - 0.28) / 0.56)) < 1e-9
    pins.append(("cin", "INPUT", "Metal2", x, die[1] + H_LEN / 2, W / 2, H_LEN / 2))
    lines = ["VERSION 5.8 ;", 'DIVIDERCHAR "/" ;', 'BUSBITCHARS "[]" ;', "DESIGN ripple_add ;",
             f"UNITS DISTANCE MICRONS {DBU} ;",
             f"DIEAREA ( {um(die[0])} {um(die[1])} ) ( {um(die[2])} {um(die[3])} ) ;",
             f"PINS {len(pins)} ;"]
    for name, d, layer, xc, y, hw, hh in pins:
        lines += [f"    - {name} + NET {name} + DIRECTION {d} + USE SIGNAL",
                  "      + PORT",
                  f"        + LAYER {layer} ( {-um(hw)} {-um(hh)} ) ( {um(hw)} {um(hh)} )",
                  f"        + PLACED ( {um(xc)} {um(y)} ) N ;"]
    lines += ["END PINS", "END DESIGN", ""]
    out.write_text("\n".join(lines))
    print(f"wrote {out}: {len(pins)} pins")


if __name__ == "__main__":
    main()
