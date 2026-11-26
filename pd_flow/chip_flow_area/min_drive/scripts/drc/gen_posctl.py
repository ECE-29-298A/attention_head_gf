# KLayout batch script: positive controls for the CO.6 check (both tools must flag them).
#   pos_co6.gds   a poly contact (0.22 um cut) with Metal1 overlapping it by only 0.005 um on every side
#                 (Magic CO.6 directional surround and KLayout CO.6a/CO.6b must fire)
#   pos_m1sp.gds  two Metal1 bars 0.10 um apart (M1.2a, 0.23 um) as a generic sanity check
# usage: klayout -b -r gen_posctl.py -rd out=<dir>
import pya, os
OUT = globals().get("out", "/tmp")
def mk(name, shapes):
    ly = pya.Layout(); ly.dbu = 0.001
    top = ly.create_cell("TOP")
    for (l, d), boxes in shapes.items():
        li = ly.layer(l, d)
        for b in boxes:
            top.shapes(li).insert(pya.DBox(*b))
    p = os.path.join(OUT, name); ly.write(p); print("wrote", p)
# poly 30/0, contact 33/0, metal1 34/0
mk("pos_co6.gds", {(30, 0): [(0, 0, 1.0, 1.0)], (33, 0): [(0.39, 0.39, 0.61, 0.61)],
                   (34, 0): [(0.385, 0.385, 0.615, 0.615)]})
mk("pos_m1sp.gds", {(34, 0): [(0, 0, 2.0, 0.5), (0, 0.6, 2.0, 1.1)]})
