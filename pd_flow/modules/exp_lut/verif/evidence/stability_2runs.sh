#!/bin/bash
# Two clean runs of the exp_lut contract (golden RTL, then the GF180 golden netlists r0 and r1);
# per-item id, status, label, ok, detail compared (timings excluded).
V="/Users/samuelzhang/Desktop/2B ECE/attention_head_gf/pd_flow/modules/exp_lut/verif"
S=/private/tmp/claude-501/-Users-samuelzhang-Desktop-2B-ECE-attention-head-gf/fdcf0a1f-422b-437c-87ae-0ead8c85435c/scratchpad/stab
mkdir -p "$S"
cd "$V" || exit 1
for n in 1 2; do
    rm -rf "$V/logs" "$V/formal/runs" "$V/results.json" "$V/run_all.console.log" \
           "$V/gate/evidence/golden_r0_gf180" "$V/gate/evidence/golden_r1_gf180"
    ./run_all.sh > /dev/null 2>&1; echo "run $n rtl rc=$?"
    ./run_all.sh --gate --registered 0 --rtl gate/netlists/exp_lut_r0_gf180.v --out gate/evidence/golden_r0_gf180 > /dev/null 2>&1; echo "run $n gate r0 rc=$?"
    ./run_all.sh --gate --registered 1 --rtl gate/netlists/exp_lut_r1_gf180.v --out gate/evidence/golden_r1_gf180 > /dev/null 2>&1; echo "run $n gate r1 rc=$?"
    cp results.json "$S/rtl_$n.json"
    cp gate/evidence/golden_r0_gf180/results.json "$S/g0_$n.json"
    cp gate/evidence/golden_r1_gf180/results.json "$S/g1_$n.json"
done
/usr/local/bin/python3 - "$S" "$V/evidence/stability_2runs.txt" <<'EOF'
import json, sys
s, out = sys.argv[1:3]
L = ["# exp_lut contract stability: 2 runs from a clean state (logs/, formal/runs/, results.json, "
     "run_all.console.log, gate/evidence/golden_r{0,1}_gf180/ deleted before each run; fresh temp build dir per run), 2026-11-26",
     "# per run: golden RTL (./run_all.sh, REGISTERED 0 and 1), then the GF180 golden netlists (--gate --registered 0 / 1);",
     "# per-item id, status, label, ok, detail compared (timings excluded)"]
def key(r): return [(i["id"], i["status"], i["label"], i["ok"], i["detail"]) for i in r["items"]]
allsame = True
for n in (1, 2):
    parts = []
    for tag in ("rtl", "g0", "g1"):
        r = json.load(open(f"{s}/{tag}_{n}.json"))
        parts.append(f'{tag} {r["mode"]} {r["items_ok"]} {r["items_total"]} {r["all_ok"]} {r["total_seconds"]}')
    L.append(f"run {n}: " + " | ".join(parts) + "   (mode items_ok items_total all_ok seconds)")
for tag in ("rtl", "g0", "g1"):
    a, b = (json.load(open(f"{s}/{tag}_{n}.json")) for n in (1, 2))
    same = key(a) == key(b)
    allsame &= same and a["all_ok"] and b["all_ok"]
    L.append(f"{tag}: {'all ' + str(len(a['items'])) + ' items identical across runs' if same else 'DIFFERENT'}")
    if not same:
        for x, y in zip(key(a), key(b)):
            if x != y: L.append(f"  diff {x} | {y}")
for tag in ("rtl", "g0", "g1"):
    r = json.load(open(f"{s}/{tag}_2.json"))
    L.append(f"\n## run 2 items ({tag})")
    for i in r["items"]:
        L.append(f'{i["id"]} {i["status"]} {i["label"]} {i["ok"]} {i["seconds"]:.2f}s {i["detail"]}')
L.append(f"\nVERDICT {'stable: both runs all ok and identical' if allsame else 'NOT STABLE'}")
open(out, "w").write("\n".join(L) + "\n")
print(L[-1])
EOF
