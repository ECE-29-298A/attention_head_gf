#!/bin/bash
# Agent 2: every RTL mutant, attack and gate mutant through the hash-checked contract copy (unmodified).
H="$(cd "$(dirname "$0")" && pwd)"
export CONTRACT_VERIF=/private/tmp/claude-501/-Users-samuelzhang-Desktop-2B-ECE-attention-head-gf/fdcf0a1f-422b-437c-87ae-0ead8c85435c/scratchpad/mac_copy/pd_flow/modules/mac_unit/verif
/usr/local/bin/python3 "$H/run_mutants.py" "$H"/mutants/*.v > "$H/mutant_runs_rtl.console.txt" 2>&1
MANIFEST_DIR=attacks /usr/local/bin/python3 "$H/run_mutants.py" "$H"/attacks/*.v > "$H/mutant_runs_attacks.console.txt" 2>&1
/usr/local/bin/python3 "$H/run_mutants.py" --gate "$H"/gate_mutants/*.v > "$H/mutant_runs_gate.console.txt" 2>&1
echo BATCH_DONE
