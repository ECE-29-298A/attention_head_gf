#!/usr/bin/env python3
"""Agent 2: markdown table + score from mutation_results.json and ref/mutant_ref_results.txt."""
import json, os, collections
HERE = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(HERE, "mutation_results.json")))["runs"]
ref = collections.defaultdict(dict)
p = os.path.join(HERE, "ref", "mutant_ref_results.txt")
if os.path.exists(p):
    for l in open(p):
        f = l.split()
        if len(f) >= 3: ref[f[0]][f[1]] = f[2]
mk = [k for k, v in d.items() if v["class"] != "equivalent"]
eq = [k for k, v in d.items() if v["class"] == "equivalent"]
print(f"must-kill {len(mk)}: killed {sum(d[k]['outcome']=='killed' for k in mk)}, "
      f"by formal {sum(bool(d[k].get('killed_by_formal')) for k in mk)}, by edge {sum(bool(d[k].get('killed_by_edge')) for k in mk)}")
print(f"equivalent {len(eq)}: survived {sum(d[k]['outcome']=='survived' for k in eq)}")
print()
print("| Run | Class | Outcome | Gating ok | Killed by | Own ref 00 / 11 |")
print("|---|---|---|---|---|---|")
for k, v in d.items():
    n = k[5:] if k.startswith("gate_") else k
    r = ref.get(n, {})
    rr = f"{r.get('00','-')} / {r.get('11','-')}" if r else "-"
    print(f"| `{k}` | {v['class']} | {v['outcome']} | {v.get('items_ok','-')}/{v.get('items_total','-')} | {', '.join(v.get('killed_by', [])) or '-'} | {rr} |")
