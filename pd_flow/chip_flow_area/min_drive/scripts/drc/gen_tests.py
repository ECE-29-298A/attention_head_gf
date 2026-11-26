# KLayout batch script (host): build DRC test layouts for the mux2_1 question.
# usage: klayout -b -r gen_tests.py -rd out=<dir>
# Writes, for DUT in {mux2_1, mux2_2 (control)}:
#   alone_<cell>.gds  one instance of <cell> (also for addf_1 = AGENT_CONTEXT reference, oai33_2, oai33_1)
#   rows_<DUT>.gds    8 abutted rows in the real row pattern (even rows N, odd rows FS, sharing rails),
#                     every row: endcap | filltie | X DUT X DUT ... | filltie | endcap, with a filltie at
#                     most every 30 sites (chip windows are 33 sites), X cycling over common neighbours,
#                     DUT and neighbour orientations varied per row pair (unflipped / flipped), and the
#                     DUT columns aligned so that DUT abuts DUT vertically across every row boundary.
#   pairs_<DUT>.gds   DUT|DUT horizontal abutment in all 4 orientation pairs, in N and FS rows.
import pya, os

PDKV = "/Users/samuelzhang/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee"
LIB = PDKV + "/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/gds/gf180mcu_fd_sc_mcu7t5v0.gds"
LEF = PDKV + "/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/lef/gf180mcu_fd_sc_mcu7t5v0.lef"
P = "gf180mcu_fd_sc_mcu7t5v0__"
OUT = globals().get("out", "/tmp")
SITE, H = 0.56, 3.92

import re
W = {}
cur = None
for line in open(LEF):
    m = re.match(r"\s*MACRO\s+(\S+)", line)
    if m:
        cur = m.group(1)
    m = re.match(r"\s*SIZE\s+([\d.]+)\s+BY\s+([\d.]+)", line)
    if m and cur:
        W[cur[len(P):]] = float(m.group(1))

NEIGH = ["inv_1", "clkinv_1", "nand2_1", "nor2_1", "and2_1", "or2_1", "aoi21_1", "oai21_1", "aoi22_1",
         "oai22_1", "nand3_1", "nor3_1", "aoi211_1", "oai211_1", "xor2_1", "xnor2_1", "mux4_1", "dffq_1",
         "buf_3", "buf_4", "clkbuf_4", "tieh", "tiel", "fill_1", "fill_2", "fillcap_4", "antenna",
         "oai32_1", "nor4_1", "nand4_1", "xor3_1", "addh_1", "mux2_2", "mux2_1"]


def new_layout():
    ly = pya.Layout()
    ly.read(LIB)
    return ly


def place(top, ly, name, x, y, orient, row_fs):
    """orient in N, FN (in an N row) or FS, S (in an FS row); x,y = lower-left of the site box"""
    c = ly.cell(P + name)
    w = W[name]
    if orient == "N":
        t = pya.DTrans(pya.DTrans.R0, x, y)
    elif orient == "FN":
        t = pya.DTrans(pya.DTrans.M90, x + w, y)
    elif orient == "FS":
        t = pya.DTrans(pya.DTrans.M0, x, y + H)
    elif orient == "S":
        t = pya.DTrans(pya.DTrans.R180, x + w, y + H)
    top.insert(pya.DCellInstArray(c.cell_index(), t))
    return w


def finish(ly, top, path):
    # keep only the top tree (drop unused library cells)
    keep = set(top.called_cells()) | {top.cell_index()}
    for ci in [c.cell_index() for c in ly.each_cell()]:
        if ci not in keep:
            ly.delete_cell(ci)
    ly.write(path)
    print("wrote", path, top.dbbox())


def alone(cell):
    ly = new_layout()
    top = ly.create_cell("TOP")
    place(top, ly, cell, 0, 0, "N", False)
    finish(ly, top, os.path.join(OUT, f"alone_{cell}.gds"))


def rows(dut):
    ly = new_layout()
    top = ly.create_cell("TOP")
    for r in range(8):
        fs = r % 2 == 1
        y = r * H
        pair = r // 2  # 0: both unflipped, 1: DUT flipped, 2: neighbours flipped, 3: both flipped
        d_or = ("S" if fs else "FN") if pair in (1, 3) else ("FS" if fs else "N")
        n_or = ("S" if fs else "FN") if pair in (2, 3) else ("FS" if fs else "N")
        x = 0.0
        x += place(top, ly, "endcap", x, y, "FS" if fs else "N", fs)
        x += place(top, ly, "filltie", x, y, "FS" if fs else "N", fs)
        since_tap = 0.0
        for i, nb in enumerate(NEIGH):
            seg = W[nb] + W[dut]
            if since_tap + seg > 30 * SITE:
                x += place(top, ly, "filltie", x, y, "FS" if fs else "N", fs)
                since_tap = 0.0
            x += place(top, ly, nb, x, y, n_or, fs)
            x += place(top, ly, dut, x, y, d_or, fs)
            since_tap += seg
        x += place(top, ly, "inv_1", x, y, n_or, fs)
        x += place(top, ly, "filltie", x, y, "FS" if fs else "N", fs)
        x += place(top, ly, "endcap", x, y, "FS" if fs else "N", fs)
    finish(ly, top, os.path.join(OUT, f"rows_{dut}.gds"))


def pairs(dut):
    ly = new_layout()
    top = ly.create_cell("TOP")
    combos = [("N", "N"), ("N", "FN"), ("FN", "N"), ("FN", "FN")]
    for r in range(2):
        fs = r == 1
        y = r * H
        x = 0.0
        x += place(top, ly, "endcap", x, y, "FS" if fs else "N", fs)
        x += place(top, ly, "filltie", x, y, "FS" if fs else "N", fs)
        for a, b in combos:
            if fs:
                a, b = {"N": "FS", "FN": "S"}[a], {"N": "FS", "FN": "S"}[b]
            x += place(top, ly, dut, x, y, a, fs)
            x += place(top, ly, dut, x, y, b, fs)
            x += place(top, ly, "filltie", x, y, "FS" if fs else "N", fs)
        x += place(top, ly, "endcap", x, y, "FS" if fs else "N", fs)
    finish(ly, top, os.path.join(OUT, f"pairs_{dut}.gds"))


os.makedirs(OUT, exist_ok=True)
for c in ["mux2_1", "mux2_2", "addf_1", "oai33_1", "oai33_2"]:
    alone(c)
for d in ["mux2_1", "mux2_2"]:
    rows(d)
    pairs(d)
