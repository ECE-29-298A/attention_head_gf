#!/usr/bin/env python3
"""Summarise KLayout .lyrdb reports: violations per rule, plus DF.13_MV/DF.14_MV explicitly.

Usage: lyrdb_summary.py OUT.json GDS REPORT.lyrdb [...]
Each violation item keeps its rule and first-polygon bounding box (um) so it can be classified.
"""
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def bbox(values_text):
    nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", values_text or "")]
    if len(nums) < 2:
        return None
    xs, ys = nums[0::2], nums[1::2]
    return [min(xs), min(ys), max(xs), max(ys)]


def main():
    out, gds, reports = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
    res = {"gds": str(gds), "gds_sha256": hashlib.sha256(gds.read_bytes()).hexdigest(),
           "reports": {}}
    for r in reports:
        root = ET.parse(r).getroot()
        cats = [c.findtext("name") for c in root.iter("category")]
        counts = {c: 0 for c in cats}
        items = []
        for it in root.iter("item"):
            cat = (it.findtext("category") or "").strip("'")
            counts[cat] = counts.get(cat, 0) + 1
            v = it.find("values")
            txt = " ".join((x.text or "") for x in v.iter("value")) if v is not None else ""
            items.append({"rule": cat, "bbox_um": bbox(txt)})
        viol = {k: v for k, v in counts.items() if v}
        res["reports"][Path(r).name] = {
            "rules_checked": len(cats), "total": sum(viol.values()), "by_rule": viol,
            "DF.13_MV": counts.get("DF.13_MV", "not-in-deck"),
            "DF.14_MV": counts.get("DF.14_MV", "not-in-deck"),
            "items": items[:200]}
        print(f"{Path(r).name}: rules={len(cats)} violations={sum(viol.values())} "
              f"DF.13_MV={counts.get('DF.13_MV', 'n/a')} DF.14_MV={counts.get('DF.14_MV', 'n/a')} "
              f"{viol}")
    out.write_text(json.dumps(res, indent=1) + "\n")


if __name__ == "__main__":
    main()
