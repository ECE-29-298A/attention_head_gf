#!/usr/bin/env python3
"""Minimal DEF NETS reader: {net: [(inst, pin), ...]} (PIN connections appear as ('PIN', name))."""
import re
def read_nets(path):
    txt = open(path).read()
    m = re.search(r"^NETS \d+ ;(.*?)^END NETS", txt, re.S | re.M)
    nets = {}
    for st in m.group(1).split(';'):
        mm = re.match(r"\s*-\s+(\S+)(.*)", st, re.S)
        if not mm: continue
        nm, rest = mm.groups()
        head = re.split(r"\+\s*(ROUTED|USE|SOURCE|WEIGHT|FIXED|COVER|NOSHIELD)", rest)[0]
        nets[nm.replace('\\', '')] = [(i.replace('\\', ''), p) for i, p in re.findall(r"\(\s*(\S+)\s+(\S+)\s*\)", head)]
    return nets
