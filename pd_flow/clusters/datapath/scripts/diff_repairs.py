#!/usr/bin/env python3
"""Per-driver difference of resizer work (upsizing and repair buffers) between two runs.
usage: diff_repairs.py <A: summary.json or area_classes.json> <B: ...>   (A is the reference)"""
import sys, json
sys.path.insert(0, __import__('os').path.dirname(__file__)); import dplib
L = dplib.liberty()
def load(p):
    j = json.load(open(p)); return j.get('area_classes', j)
A, B = load(sys.argv[1]), load(sys.argv[2])
lab = {n: v['label'] for n, v in json.load(open(dplib.ATTR_JSON))['cells'].items()}
tot = 0.0
for n in sorted(set(A['upsized']) | set(B['upsized']) | set(A['repair_by_driver']) | set(B['repair_by_driver'])):
    ua = A['upsized'].get(n); ub = B['upsized'].get(n)
    ra = sorted(m for _, m in A['repair_by_driver'].get(n, [])); rb = sorted(m for _, m in B['repair_by_driver'].get(n, []))
    da = (ua[2] if ua else 0) + sum(L[m]['area'] for m in ra); db = (ub[2] if ub else 0) + sum(L[m]['area'] for m in rb)
    if abs(da - db) > 1e-6 or (ua and ub and ua[1] != ub[1]):
        tot += db - da
        print(f"{n:9s} {lab.get(n, '?'):20s} A: {ua[1] if ua else '-':9s} {ra}  B: {ub[1] if ub else '-':9s} {rb}  d {db - da:+7.2f}")
print(f'total upsize+repair delta B-A {tot:+.2f}')
