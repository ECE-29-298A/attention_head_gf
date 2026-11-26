# ripple_add: Phase 2 architectural area optimization (Agent 3)

Date: 2026-11-26. **Result: the original RTL is retained.** `best/ripple_add.v` is a
byte-identical copy of `baseline/original_rtl/ripple_add.v` (SHA-256 `5977cad9…90cf7a`).

No candidate was smaller at both instantiated widths without a material timing loss. The
formulations that map smaller (behavioural `a + b + cin`, majority or alternating-polarity
carries) all give a slower carry chain under the unchanged ABC recipe. Under this recipe the
original sits on the area/delay Pareto front.

## Method (identical for every attempt)

| Step | How |
|---|---|
| Lint + contract | `verilator --lint-only -Wall` (N=22, 12; logs `runs/<c>/lint_n*.log`) and the frozen contract `verif/run_all.sh --rtl <c> --out runs/<c>/contract` (68 items, hash `b879560878477abf`, not modified) |
| Equivalence | EQY, SAT strategy, depth 1 (complete for combinational logic), **golden original** vs candidate at N=12 and N=22. No assumptions, cutpoints or black boxes (`eqy_template.eqy`, logs `runs/<c>/eqy/`) |
| Area | `scripts/synth_area.py --rtl runs/<c>/rtl` with the recipe unchanged. `rtl/` is a full copy of `original_rtl` with only `ripple_add.v` replaced. Targets: ripple_add_22, ripple_add_12, mac_unit (OUTPUTS=8), tt_um_attention_head_gf (8) |
| Timing | Same-recipe netlists (`verif/gate/synth_gf180.sh`, areas checked equal to synth_area). OpenSTA 2.7.0 in librelane:3.0.14 (`sta.tcl`, `sta_run.sh`). Input transition **0.30 ns** on all inputs, **0.02 pF** load on all outputs (about four drive-1 input pins), virtual 100 ns clock, zero I/O delay, no wire load. Liberty TT 025C 3V30 and SS 125C 3V00. Metric: worst a/b/cin to s arrival |
| Acceptance | Contract all ok; EQY PASS at both N; module area lower at N=22 **and** N=12; mac_unit and top lower than the original; worst N=22 path at most **5 %** longer at TT and SS ("materially worse" = more than 5 %) |

Scripts: `eval_full.sh` (steps 1 to 4 per candidate), `area_eval.sh`, `sta_run.sh`,
`collect.py`, `build_attempts.py` (builds `attempts.json` with every number and decision).

## Attempts

Golden: N=22 2,146.91 µm² (95 cells), N=12 1,148.09, mac_unit 20,573.41, top 42,145.64;
N=22 path 10.594 ns TT / 21.319 ns SS (b[0] to s[21]).

| # | Candidate | N=22 µm² | N=12 µm² | mac_unit | top | t22 TT ns (Δ) | t22 SS ns (Δ) | Contract | EQY 12/22 | Decision |
|---|---|---:|---:|---:|---:|---:|---:|---|---|---|
| – | golden (original) | 2146.91 | 1148.09 | 20573.41 | 42145.64 | 10.594 | 21.319 | 68/68 | PASS/PASS | retained |
| c01 | behavioural `a+b+cin` ($alu) | **2107.39** | **1132.72** | 20472.44 | 41138.05 | 11.857 (+11.9 %) | 24.161 (+13.3 %) | 68/68 | PASS/PASS | reject: timing |
| c02 | `{a,1}+{b,cin}` >> 1 | 2105.20 | 1148.09 | 20351.70 | 41094.14 | 11.201 (+5.7 %) | 22.699 (+6.5 %) | 60/68 (lint: unused t[0]) | PASS/PASS | reject: lint, N=12 not lower, timing |
| c03 | majority carry | 2230.32 | 1172.24 | 20294.62 | 41662.70 | 11.083 (+4.6 %) | 22.924 (+7.5 %) | 68/68 | PASS/PASS | reject: area |
| c04 | XOR-shared p, mux carry `p?c:a` | 2212.76 | 1123.94 | 20362.68 | 41653.92 | 11.592 (+9.4 %) | 23.750 (+11.4 %) | 68/68 | PASS/PASS | reject: N=22 area, timing |
| c05 | alternating-polarity (inverted) carry | 2122.76 | 1108.58 | 20336.33 | 41282.93 | 15.376 (+45.1 %) | 31.458 (+47.6 %) | 68/68 | PASS/PASS | reject: timing |
| c06 | explicit g/p vectors | 2146.91 | 1148.09 | 20446.09 | 41293.91 | 10.594 (0) | 21.319 (0) | 60/68 (lint: unused g[N-1]) | PASS/PASS | reject: lint, area equal |
| c06b | c06, lint-clean | 2146.91 | 1148.09 | 20428.53 | 42488.10 | 10.594 (0) | 21.319 (0) | 68/68 | PASS/PASS | reject: area equal, top higher |
| c07 | OR-propagate carry | 2171.05 | 1174.43 | 20382.43 | 41454.16 | 11.179 (+5.5 %) | 23.113 (+8.4 %) | 68/68 | PASS/PASS | reject: area |
| c08 | uniform inverted carry | 2210.57 | 1185.41 | 20336.33 | 41623.19 | 10.876 (+2.7 %) | 22.110 (+3.7 %) | 68/68 | PASS/PASS | reject: area |
| c09 | alternating aoi22/oai21-shaped | 2140.32 | 1156.87 | 20529.51 | 41517.82 | 13.023 (+22.9 %) | 26.769 (+25.6 %) | 68/68 | PASS/PASS | reject: N=12 area, timing |
| c10 | POS carry `(a\|b)&(ab\|c)` | 2116.17 | 1152.48 | 20468.04 | 41476.11 | 13.412 (+26.6 %) | 27.569 (+29.3 %) | 68/68 | PASS/PASS | reject: N=12 area, timing |
| c11 | mux carry `p?c:b` | 2212.76 | 1167.85 | 20560.24 | 41274.15 | 11.592 (+9.4 %) | 23.750 (+11.4 %) | 68/68 | PASS/PASS | reject: area |
| c12 | behavioural `a+(b+cin)` | 2107.39 | 1132.72 | 20408.77 | 41111.71 | 11.857 (+11.9 %) | 24.161 (+13.3 %) | 68/68 | PASS/PASS | reject: timing |
| c14 | behavioural `a-~b-(1-cin)` | 3009.62 | 1499.32 | 21221.00 | 41945.88 | 10.552 (-0.4 %) | 21.364 (+0.2 %) | 68/68 | PASS/PASS | reject: area |
| c15 | golden with shared p wire | 2146.91 | 1148.09 | 20428.53 | 42488.10 | 10.594 (0) | 21.319 (0) | 68/68 | PASS/PASS | reject: area equal |
| c16 | majority, search-tuned operand order | **2096.42** | **1099.80** | 20476.83 | 41414.64 | 16.103 (+52.0 %) | 33.006 (+54.8 %) | 68/68 | PASS/PASS | reject: timing |
| c17 | alt-polarity majority, search-tuned | **2083.24** | 1115.16 | 20127.79 | 41491.48 | 15.458 (+45.9 %) | 31.649 (+48.5 %) | 68/68 | PASS/PASS | reject: timing |

(c13 was a duplicate of c01 and was dropped. N=12 timing is in `attempts.json`.)

Every contract failure is a lint failure caused by an unused bit. Every candidate is
EQY-proven equivalent to the original at both widths.

## Findings

1. **Area/delay trade-off, not a free win.** Five candidates (c01, c05, c12, c16, c17) are
   smaller at both widths. The best are c17 at N=22 (−63.7 µm², −3.0 %) and c16 at N=12
   (−48.3 µm², −4.2 %). All five are 12 to 55 % slower. The behavioural $alu form (c01) is the
   best compromise: −39.5 / −15.4 µm² (−1.8 % / −1.3 %) for +11.9 % TT and +13.3 % SS.
2. **Operand-order search** (`search/`): 240 generated variants in 8 carry formulations, with
   operand order shuffled. Family medians are mostly *larger* than the original. 24 variants
   were smaller at both widths. STA-screened (`search/sta_screen/`), every one of them is at
   least 21.8 % slower (best 12.899 ns TT). Of the original's form, 23 of 26 generated
   reorderings map identically (2,146.91 / 1,148.09) and 3 map larger (2,157.9 / 1,246.9,
   first round `quick1.txt`). None of them maps smaller.
3. **Top-level area is dominated by ABC tie-break noise** (`runs/_noise/`). 43 rewrites of the
   original that are functionally and structurally identical (renames, a comment, operand
   order) all give the same module area. Their mac_unit area spans 20,349.5 to 21,043.2
   (median 20,540.5) and their top area spans 40,995.4 to 42,145.6 (median 41,584.8). The
   original's 42,145.64 is the *maximum* of its own family. Renames and comments are exactly
   neutral; operand order alone moves top by up to 1,150 µm² (2.7 %). The −1,008 µm² top-level
   delta of c01 is therefore inside the noise band. The real adder saving is the 55 µm² seen at
   module level. **Do not read top-level deltas under about 1.2k µm² as caused by a module edit
   under this recipe.** This applies to every module's Phase 2.
4. The chip's worst SS setup path (baseline harden, `max_ss_125C_3v00/max.rpt`, 60.28 ns
   arrival, +41.79 ns slack) is dominated by an alternating oai21/aoi21 chain, the signature of
   this mapped ripple adder. Adder delay is therefore likely to add directly to chip WNS. This
   is not proven by name tracing, because the netlist is flattened.

## Notes for Phase 3 (cell-level structuring; probe only, not a candidate)

`phase3_probe/addf_chain_n{22,12}.v` is a hand-instantiated `addf_1` chain. The gate-level
contract (`--gate`) passes on both: N=22 10/10, N=12 11/11.

| | Area µm² | vs golden | t TT ns | t SS ns |
|---|---:|---:|---:|---:|
| addf_1 chain N=22 | 1,593.72 (22 cells) | −25.8 % | 19.908 (+88 %) | 41.429 (+94 %) |
| addf_1 chain N=12 | 869.30 (12 cells) | −24.3 % | 11.172 (+83 %) | 23.195 (+90 %) |

`addf` saves about 25 % of the area but roughly doubles the ripple delay, because CI to CO
through `addf_1` is about 0.9 ns TT against about 0.45 ns per bit for the oai21/aoi21 chain.
At N=22 SS this is about +20 ns. Against +41.8 ns of chip slack it probably fits, if the
adder is on the critical path as finding 4 suggests, but it must be checked at chip level.
Options for Phase 3 to evaluate: a mix of addf with a fast carry on the top bits, or
`addf_2`/`addh` for the cin=0 N=12 instance (its LSB can be a half adder). ABC never infers
multi-output cells, so this saving is reachable only by explicit cell structuring.

## Files

- `candidates/*.v`: every attempted RTL. `best/ripple_add.v` is the original (retained).
- `runs/<c>/`: `contract/` (results.json, logs, formal runs), `eqy/`, `area.json`, `rtl/`,
  `netlist_n{22,12}.v` (+ stat), `sta/` logs. `runs/collected.json` is the merged table.
- `runs/_noise/`: noise study (n01–n08 cosmetic, p01–p35 operand orders of the original,
  v01–v06 orders of the behavioural form).
- `search/`: generator `gen.py`, module-level results `quick{1,2,3}.txt`, `sta_screen/`.
- `attempts.json`: all numbers, per-attempt decision and reasons, noise and search summaries,
  Phase 3 probe.
