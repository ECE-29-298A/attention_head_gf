# KLayout batch script (host KLayout Python): the TT precheck's layout-level non-DRC checks for gf180mcuD,
# re-implemented with pya on the logic of tt/precheck/precheck.py (klayout_checks, layer_check,
# cell_name_check), using the precheck's own tables (tt/precheck/tech_data.py, klayout_tools.py).
# Not covered: boundary_check (template DEF), power_pin_check (LEF/Verilog), pin_check, analog pins,
# Verilog syntax. None of them depends on which standard cells are placed.
# usage: klayout -b -r tt_layout_checks.py -rd gds=<file> -rd top=<name> -rd lyp=<gf180mcu.lyp> -rd precheck=<tt/precheck>
import re
import sys
import pya

sys.path.insert(0, precheck)  # noqa: F821  (KLayout -rd variable)
from tech_data import forbidden_layers, boundary_layer, valid_layers  # noqa: E402
from klayout_tools import parse_lyp_layers  # noqa: E402

tech = "gf180mcuD"
ly = pya.Layout()
ly.read(gds)  # noqa: F821
fails = []
if ly.top_cell().name != top:  # noqa: F821
    fails.append(f"top name {ly.top_cell().name} != {top}")  # noqa: F821
layers = parse_lyp_layers(lyp, True)  # noqa: F821
for name in forbidden_layers[tech]:
    li = layers[name]
    if ly.find_layer(li.layer, li.data_type) is not None:
        fails.append(f"forbidden layer {name} present")
bl = layers[boundary_layer[tech]]
if ly.find_layer(bl.layer, bl.data_type) is None:
    fails.append(f"boundary layer {boundary_layer[tech]} missing")
alll = parse_lyp_layers(lyp, False)  # noqa: F821
valid = {(alll[n].layer, alll[n].data_type) if isinstance(n, str) else tuple(n) for n in valid_layers[tech]}
present = set()
for idx in ly.layer_indexes():
    info = ly.get_info(idx)
    if any(not c.shapes(idx).is_empty() for c in ly.each_cell()):
        present.add((info.layer, info.datatype))
excess = present - valid
if excess:
    fails.append(f"invalid layers {sorted(excess)}")
bad = sorted(c.name for c in ly.each_cell() if re.search(r"[^A-Za-z0-9_$-]", c.name))
if bad:
    fails.append(f"invalid cell names {bad[:5]}")
print(f"{gds}: layers {len(present)}, cells {ly.cells()}, " + ("PASS" if not fails else "FAIL " + "; ".join(fails)))  # noqa: F821
