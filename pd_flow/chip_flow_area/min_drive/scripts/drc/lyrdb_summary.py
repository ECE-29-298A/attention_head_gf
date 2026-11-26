#!/usr/bin/env python3
"""Summarize a KLayout .lyrdb report: total items and items per category (rule).
usage: lyrdb_summary.py <report.lyrdb> [--json out.json]"""
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter

p = sys.argv[1]
root = ET.parse(p).getroot()
cnt = Counter()
for it in root.iter("item"):
    c = it.findtext("category") or "?"
    cnt[c.strip("'")] += 1
tot = sum(cnt.values())
print(f"total {tot} items: " + ", ".join(f"{k}={v}" for k, v in sorted(cnt.items())))
if "--json" in sys.argv:
    json.dump({"report": p, "total": tot, "by_rule": dict(sorted(cnt.items()))},
              open(sys.argv[sys.argv.index("--json") + 1], "w"), indent=1)
