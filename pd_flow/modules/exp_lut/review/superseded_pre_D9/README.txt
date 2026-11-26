Agent 2 artifacts produced BEFORE user directive D9 ("do NOT do exhaustive testing; you MUST use
formal verification techniques"). They used the pre-amendment contract (commit ec61c41) whose
sim_exh_* / ivl_exh_* items are exhaustive simulation, and Agent 2's own exhaustive Verilator
sweeps (ref/exhaustive_sweep.cpp). They are kept for traceability only and are NOT evidence for
the review verdict. The campaign was stopped on the coordinator's instruction after 14 mutants
(m10 was interrupted).
  mutation_results.json, mutation_runs/, mutant_runs_rtl.console.txt  partial RTL campaign
  mutant_check/, gate_check/, out/   Agent 2 exhaustive-sweep reference runs (mutant classification)
  clean_copy_rtl/                     clean-copy rerun of the golden (29/29, identical to Agent 1)
