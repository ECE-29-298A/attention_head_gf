#!/usr/bin/env python3
"""placement.json -> minimal DEF (COMPONENTS only), used as --init-def seed. usage: pl2def.py P.json OUT.def"""
import sys, json
pl = json.load(open(sys.argv[1]))['cells']
with open(sys.argv[2], 'w') as f:
    f.write('VERSION 5.8 ;\nUNITS DISTANCE MICRONS 2000 ;\nDIEAREA ( 0 0 ) ( 693280 321440 ) ;\n' + f'COMPONENTS {len(pl)} ;\n')
    for n, c in pl.items(): f.write(f"    - {n} gf180mcu_fd_sc_mcu7t5v0__{c['master']} + PLACED ( {round(c['x'] * 2000)} {round(c['y'] * 2000)} ) {c['orient']} ;\n")
    f.write('END COMPONENTS\nEND DESIGN\n')
