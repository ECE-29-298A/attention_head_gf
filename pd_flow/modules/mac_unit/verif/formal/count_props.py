#!/usr/bin/env python3
"""Count assert and cover cells in an SBY model/design.json (Yosys JNY format). Guards
against vacuous or mis-configured runs: run_all.sh checks the count expected for each task."""
import json
import sys

d = json.load(open(sys.argv[1]))
n = {"assert": 0, "cover": 0}
for m in d["modules"]:
    for cs in m.get("cell_sorts", []):
        for c in cs.get("cells", []):
            if cs["type"] in ("$assert", "$cover"):
                n[cs["type"][1:]] += 1
            elif cs["type"] == "$check":
                fl = c.get("parameters", {}).get("FLAVOR")
                if fl in n:
                    n[fl] += 1
print(f"asserts={n['assert']} covers={n['cover']}")
