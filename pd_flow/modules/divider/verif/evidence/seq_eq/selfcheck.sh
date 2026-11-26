#!/bin/bash
# Amendment A-1 self-check of seq_eq: golden + lemmas (default run), a renamed / re-encoded
# rewrite with and without its lemmas, the 3 smoke mutants (with the golden's lemmas), a lemma
# file containing an assume (must be rejected) and a false lemma (must fail).
V="/Users/samuelzhang/Desktop/2B ECE/attention_head_gf/pd_flow/modules/divider/verif"
S=/private/tmp/claude-501/-Users-samuelzhang-Desktop-2B-ECE-attention-head-gf/fdcf0a1f-422b-437c-87ae-0ead8c85435c/scratchpad/seq_selfcheck
G="$V/../snapshot/divider.v"; E="$V/evidence/seq_eq"; M="$V/evidence/smoke_mutants"
mkdir -p "$S"; cd "$V" || exit 1
run() { # tag rtl [lemmas]
    local tag=$1 rtl=$2 lem=${3:-}
    ./run_all.sh --rtl "$rtl" --out "$S/$tag" ${lem:+--lemmas "$lem"} > /dev/null 2>&1
    echo "$tag rc=$?"
}
run c_rename        "$E/c_rename.v" "$E/c_rename_lemmas.sv"
run c_rename_nolem  "$E/c_rename.v"
run m_tie           "$M/m_tie.v"     "$V/formal/golden_self_lemmas.sv"
run m_shift         "$M/m_shift.v"   "$V/formal/golden_self_lemmas.sv"
run m_restart       "$M/m_restart.v" "$V/formal/golden_self_lemmas.sv"
run golden_assume   "$G" "$E/bad_assume_lemmas.sv"
run golden_false    "$G" "$E/false_lemma_lemmas.sv"
/usr/local/bin/python3 - "$S" "$E/selfcheck.txt" <<'PYEOF'
import json, sys
s, out = sys.argv[1:3]
want = {"c_rename": "all_ok (equiv via seq_eq; eqy_rtl fails on the renamed state)",
        "c_rename_nolem": "not all_ok (no lemmas: seq_eq not-proven, eqy_rtl failed)",
        "m_tie": "not all_ok; seq_eq failed with a counterexample",
        "m_shift": "not all_ok; seq_eq failed with a counterexample",
        "m_restart": "not all_ok; seq_eq failed with a counterexample",
        "golden_assume": "lemma file rejected (lemma_lint and seq_eq failed)",
        "golden_false": "seq_eq failed (the false lemma is refuted)"}
L = ["# seq_eq (amendment A-1) self-check; runs: ./run_all.sh --rtl X [--lemmas F] --out <scratchpad>/<tag>, --jobs 3"]
for tag, w in want.items():
    r = json.load(open(f"{s}/{tag}/results.json"))
    it = {i["id"]: i for i in r["items"]}
    bad = [i["id"] for i in r["items"] if i["gating"] and not i["ok"]]
    L.append(f"{tag}: expected {w}")
    L.append(f"  all_ok={r['all_ok']} gating {r['gating_ok']}/{r['gating_total']} {r['total_seconds']}s lemmas_sha256={(r.get('seq_eq_lemmas_sha256') or '-')[:16]}; failing gating items: {' '.join(bad) or '-'}")
    for k in ("lemma_lint", "eqy_rtl_00", "eqy_rtl_11", "seq_eq_00", "seq_eq_11", "equiv_00", "equiv_11", "fv_result_00", "fv_result_11"):
        if k in it:
            L.append(f"  {k}: {it[k]['status']} - {it[k]['detail'][:150]}")
open(out, "w").write("\n".join(L) + "\n")
print("\n".join(L))
PYEOF
