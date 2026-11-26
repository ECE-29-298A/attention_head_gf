#!/usr/bin/env python3
"""Write the per-run override files of the minimum-drive experiment into ../overrides/.
Each file is applied on top of the h2 overrides by run_md.sh (an experiment key replaces the h2 key,
so EXTRA_EXCLUDED_CELLS always restates the h2 entries)."""
import json
import os
import families as F

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "overrides")
H2X = F.full(F.H2_EXCLUDED)
BUF3 = F.lef_areas()["buf_3"]
# the 11 h2 resizes whose area delta exceeds one buf_3 (upsize_diff.py on h2 step 32)
H2_EXPENSIVE = ["_1162_", "_1381_", "_1785_", "_1905_", "_2137_", "_1617_", "_1742_", "_1778_",
                "_1988_", "_1417_", "_1925_"]

runs = {
    "m0_ctrl": {},
    "m1_minall": {"EXTRA_EXCLUDED_CELLS": H2X + F.full(F.above_min())},
    "m2_no4": {"EXTRA_EXCLUDED_CELLS": H2X + F.full(F.drive_at_least(4))},
    "m3_cost": {"EXTRA_EXCLUDED_CELLS": H2X + F.full(F.cost_above(BUF3))},
    "m4_dtrx": {"RSZ_DONT_TOUCH_RX": "^_[0-9]+_$"},
    "m5_dtlist": {"RSZ_DONT_TOUCH_LIST": H2_EXPENSIVE},
    "m6_rmbuf": {"DESIGN_REPAIR_REMOVE_BUFFERS": True},
}
# mux2_1 allowed: a design-level PNR_EXCLUDED_CELL_FILE (it overrides the PDK value; LibreLane uses it for
# synthesis AND PnR) that keeps only the PDK's other entry, oai33_2.
MUX21 = {"PNR_EXCLUDED_CELL_FILE": "dir::pnr_exclude_md.cells",
         "__src_files__": {"pnr_exclude_md.cells": "# PDK drc_exclude.cells without mux2_1 (chip_flow_area/min_drive)\n"
                                                   + F.PFX + "oai33_2\n"}}
runs.update({
    "m0_ctrl_s55": {},
    "m2_no4_s55": runs["m2_no4"],
    "x0_mux21": dict(MUX21),
    "x2_mux21_no4": dict(MUX21, EXTRA_EXCLUDED_CELLS=runs["m2_no4"]["EXTRA_EXCLUDED_CELLS"]),
    # hold-safer variants of x0 (the h3 idea from chip_flow_area: a stronger CTS root buffer)
    "x3_mux21_root16": dict(MUX21, CTS_ROOT_BUFFER=F.PFX + "clkbuf_16"),
    "x4_mux21_root12": dict(MUX21, CTS_ROOT_BUFFER=F.PFX + "clkbuf_12"),
    "x0_full": dict(MUX21),
})
if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for tag, o in runs.items():
        with open(os.path.join(OUT, f"{tag}.json"), "w") as f:
            json.dump(o, f, indent=1)
        print(tag, {k: (len(v) if isinstance(v, list) else v) for k, v in o.items()})
