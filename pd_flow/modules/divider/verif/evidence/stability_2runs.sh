#!/bin/bash
# Two clean runs of the divider contract: golden RTL (configs 00 and 11), the GF180 golden
# netlists 00 and 11, and the 00 netlist with a CTS-style clock buffer; per-item id, status,
# label, ok, detail compared (timings excluded). Runs one contract at a time (--jobs 3).
# Gate runs pass evidence/seq_eq/golden_gate_lemmas.sv for seq_eq (amendment A-1).
V="/Users/samuelzhang/Desktop/2B ECE/attention_head_gf/pd_flow/modules/divider/verif"
S=/private/tmp/claude-501/-Users-samuelzhang-Desktop-2B-ECE-attention-head-gf/fdcf0a1f-422b-437c-87ae-0ead8c85435c/scratchpad/div_stab
mkdir -p "$S"
cd "$V" || exit 1
for n in 1 2; do
    rm -rf "$V/logs" "$V/formal/runs" "$V/results.json" "$V/run_all.console.log" \
           "$V/gate/evidence/golden_00_gf180" "$V/gate/evidence/golden_11_gf180" "$V/gate/evidence/clkbuf_00"
    ./run_all.sh > /dev/null 2>&1; echo "run $n rtl rc=$?"
    ./run_all.sh --gate --config 00 --lemmas evidence/seq_eq/golden_gate_lemmas.sv --rtl gate/netlists/divider_00_gf180.v --out gate/evidence/golden_00_gf180 > /dev/null 2>&1; echo "run $n gate 00 rc=$?"
    ./run_all.sh --gate --config 11 --lemmas evidence/seq_eq/golden_gate_lemmas.sv --rtl gate/netlists/divider_11_gf180.v --out gate/evidence/golden_11_gf180 > /dev/null 2>&1; echo "run $n gate 11 rc=$?"
    ./run_all.sh --gate --config 00 --lemmas evidence/seq_eq/golden_gate_lemmas.sv --rtl gate/netlists/divider_00_clkbuf_gf180.v --out gate/evidence/clkbuf_00 > /dev/null 2>&1; echo "run $n gate 00 clkbuf rc=$?"
    cp results.json "$S/rtl_$n.json"
    cp gate/evidence/golden_00_gf180/results.json "$S/g00_$n.json"
    cp gate/evidence/golden_11_gf180/results.json "$S/g11_$n.json"
    cp gate/evidence/clkbuf_00/results.json "$S/cb_$n.json"
done
/usr/local/bin/python3 - "$S" "$V/evidence/stability_2runs.txt" <<'PYEOF'
import json, sys
s, out = sys.argv[1:3]
L = ["# divider contract stability: 2 runs from a clean state (logs/, formal/runs/, results.json, run_all.console.log,",
     "# gate/evidence/{golden_00_gf180,golden_11_gf180,clkbuf_00}/ deleted before each run; fresh temp build dir per run)",
     "# per run: golden RTL (configs 00 and 11), GF180 golden netlists 00 and 11, the 00 netlist with a clock buffer;",
     "# per-item id, status, label, ok, detail compared (timings excluded)"]
key = lambda r: [(i["id"], i["status"], i["label"], i["ok"], i["detail"]) for i in r["items"]]
tags = ("rtl", "g00", "g11", "cb")
allsame = True
for n in (1, 2):
    parts = []
    for tag in tags:
        r = json.load(open(f"{s}/{tag}_{n}.json"))
        parts.append(f'{tag} {r["mode"]} gating {r["gating_ok"]}/{r["gating_total"]} all_ok={r["all_ok"]} {r["total_seconds"]}s')
    L.append(f"run {n}: " + " | ".join(parts))
for tag in tags:
    a, b = (json.load(open(f"{s}/{tag}_{n}.json")) for n in (1, 2))
    same = key(a) == key(b)
    allsame &= same and a["all_ok"] and b["all_ok"]
    L.append(f"{tag}: {'all ' + str(len(a['items'])) + ' items identical across runs' if same else 'DIFFERENT'}")
    if not same:
        for x, y in zip(key(a), key(b)):
            if x != y: L.append(f"  diff {x} | {y}")
for tag in tags:
    r = json.load(open(f"{s}/{tag}_2.json"))
    L.append(f"\n## run 2 items ({tag})")
    for i in r["items"]:
        L.append(f'{i["id"]} {i["status"]} {i["label"]} ok={i["ok"]} gating={i["gating"]} {i["seconds"]:.2f}s {i["detail"]}')
L.append(f"\nVERDICT {'stable: both runs all ok and identical' if allsame else 'NOT STABLE'}")
open(out, "w").write("\n".join(L) + "\n")
print(L[-1])
PYEOF
