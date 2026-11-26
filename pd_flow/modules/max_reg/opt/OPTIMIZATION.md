# max_reg: Phase 2 architectural area optimization (Agent 3)

Date: 2026-11-26. Verdict: **original RTL retained.** `opt/best/max_reg.v` is byte-identical to
`baseline/original_rtl/max_reg.v` (SHA-256 `d7cdf381…`).

The best candidate is c10, an LSB-first majority-ripple compare with a tie don't-care. It is
EQY-proven equivalent, passes the frozen contract 17/17, and lowers shipped-flow synthesis area
by 134 to 180 µm² across 4 of its 5 distinct rewrites. A full harden of its best text reversed
that result:
- std-cell area +254.7 µm² (more buffer, hold-delay and clock-buffer cells);
- ss setup WNS −1.57 ns;
- power +10.3%, which is outside the harden noise samples.

The gain is real in synthesis but small (≤0.5% of the chip). Harden noise is ±200 to 400 µm², so
the gain does not survive it.

## Method
- Candidates are in `candidates/`, the golden noise rewrites in `noise/`, and the cosmetic
  variants of the golden and of the candidate families in `variants/` (made by
  `make_variants.py`, which applies the same 8 transforms to each). The final c10 text is in
  `c10_clean/`, the context-only probe in `context_only/`, and the EQY negative controls in
  `negctl/`.
- `verify.sh <v> [contract]` runs three checks:
  - Verilator `-Wall` lint, with the file as `max_reg.v`.
  - EQY against the golden original: the reviewer's template, `sat` depth 1, with the 22 M
    flops matched by name. There are no assumptions, cutpoints or black boxes. Because both
    sides have the same state encoding, this is an unbounded proof.
  - The frozen `verif/run_all.sh --rtl <v> --out runs/<name>/contract`.
- EQY negative controls x01 (wrong bit-0 decision) and x02 (wrong propagate term) both
  **FAIL**, as required.
- `area_eval.sh` runs `synth_area.py` (module level, exploration only). `ship_queue.sh` runs
  `scripts/ll_synth.sh` on a full copy of original_rtl with only max_reg.v replaced, 2 at a
  time. The netlists and `stat.json` files are in `shipped_flow/`.
- `cone.py` gives the in-context max_reg area in a shipped netlist: the 22 M flops plus the cells
  whose fanout stays inside the fan-in cone of their D pins. `rest = chip − max_reg`. Splitting
  the chip this way shows whether a chip delta comes from max_reg or from ABC reshuffling the
  rest of the chip.
- `collect.py` writes `runs/collected.json`, and `build_attempts.py` writes `attempts.json`.

## Flops: no legitimate removal
- **Standalone:** M is free at power-up and the contract checks all 2^44 (M, S_in) pairs. All 22
  bits are observable, so no flop can be removed while passing the standalone contract.
- **Context:** pass-1 scores are sums of 64 INT8×INT8 products, so they lie in
  [−1,040,384, 2^20]. That is 2,088,961 values, which is below 2^21. A 21-bit encoding
  therefore exists in principle. The only cheap re-encoding is to drop bit 21 and rebuild it as
  `M[21] = M[20] & |M[19:0]`.
  - Probe k01 (`context_only/`, not proven, area only): module +151.5 µm², chip +241.5 µm².
  - The 20-input OR costs more than the dffq + mux it saves (92 µm²).
  - Rejected. No other narrowing is possible: bit 20 separates 2^20 from 0.

## Shipped-flow noise band (golden rewrites)
Distinct chip areas, in µm²:

| Sample | Area |
|---|---:|
| n05 / g_v4 | 41,063.4 |
| n06 | 41,076.6 |
| **base** (also n01, n02, n04, g_v1, g_v7, g_v8, which are byte-identical) | 41,116.1 |
| n03 / g_v2 | 41,197.3 |
| g_v3 / g_v6 | 41,348.8 |
| g_v5 | 41,351.0 |
| ripple_add n03 | 41,100.7 |
| ripple_add n04 | 41,201.7 |

The band is **[41,063.4, 41,351.0], i.e. −52.7 / +234.9 around the base.** The flow is
deterministic: comment and rename edits give byte-identical netlists.

## Attempts
All candidates pass lint, EQY against the golden (proven), and the contract (17/17).

| # | Formulation | module µm² (synth_area) | chip µm² (ll_synth) | Δ chip | in-context max_reg | rest of chip | Decision |
|---|---|---:|---:|---:|---:|---:|---|
| golden | `S_in > M` | 3,360.9 | 41,116.1 | 0 | 2,954.7 | 38,161.4 | **retained** |
| c01 | `>=` (reviewer lead) | 3,036.0 | 41,113.9 | −2.2 | 2,983.3 | 38,130.6 | rejected: in band; the module gain is ABC noise (n06, a pure operand swap, also shows −296 at module level) |
| c02 | `!(M > S_in)` | 3,367.4 | 41,357.6 | +241.5 | 3,009.6 | 38,348.0 | rejected |
| c03 | 23-bit `M − S_in`, sign | 3,071.1 | 41,357.6 | +241.5 | 3,009.6 | 38,348.0 | rejected |
| c04 | 23-bit `S_in − M`, !sign (ge) | 3,027.2 | 40,949.3 | −166.8 | 2,974.5 | 37,974.8 | rejected: gain is all rest-of-chip (max_reg +19.8); variants −226 to +99 |
| c05 | offset-binary unsigned `>` | 3,492.6 | 41,074.4 | −41.7 | 2,869.1 | 38,205.3 | rejected: in band |
| c06 | offset-binary unsigned `>=` | 3,033.8 | 41,221.5 | +105.4 | 2,908.6 | 38,312.9 | rejected |
| c07 | carry out of S + ~M (offset binary) | 3,117.2 | 41,289.5 | +173.4 | 2,924.0 | 38,365.5 | rejected |
| c08 | majority ripple, cin 0 | 2,921.8 | 40,988.8 | −127.3 | 2,831.8 | 38,157.0 | rejected: variants up to +805.6 |
| c09 | majority ripple, cin 1 (ge) | 2,926.2 | 40,944.9 | −171.2 | 2,776.9 | 38,168.0 | rejected: variants up to +384.2 |
| c10 | majority ripple, tie don't-care `c[1]=S_in[0]` | 2,921.8 | 40,982.2 | −133.9 | 2,770.3 | 38,211.9 | best family; hardened, then rejected (below) |
| c11 | alternating-polarity ripple | 2,882.3 | 40,969.0 | −147.1 | 2,757.2 | 38,211.8 | rejected: variants up to +531.2 |
| c12 | mux-chain ripple `(S^M)?S:c` | 2,856.0 | 41,254.4 | +138.3 | 2,697.9 | 38,556.5 | rejected: smallest logic, unlucky chip (−199.8 to +309.5) |
| c13 | log-depth tree comparator | 3,079.9 | 41,372.9 | +256.8 | 2,921.8 | 38,451.1 | rejected |
| c14 | `M <= S_in` | 3,369.6 | 41,535.4 | +419.3 | 2,989.9 | 38,545.5 | rejected |
| k01 | context-only: 21 flops, rebuilt M[21] | 3,512.3 | 41,357.6 | +241.5 | – | – | rejected: area probe, not proven |

### Paired variant spread (same transform on golden and candidate, Δ against the golden variant)

| Transform | golden chip | c09 | c10 | c11 | c12 |
|---|---:|---:|---:|---:|---:|
| base (`&&`, `\|\|`) | 41,116.1 | −171 | −134 | −147 | +138 |
| v2 and-swap | 41,197.3 | −224 | −242 | −103 | −143 |
| v3 bitwise `&`, `\|` | 41,348.8 | −171 | +97 | +299 | −432 |
| v4 nested if | 41,063.4 | +437 | **−127 (40,936.1)** | −53 | +248 |
| v5 distributed `en` | 41,351.0 | −400 | −384 | −378 | +75 |

c10 is the most robust family: in-context max_reg logic is −184 to −246 in every variant, and
4 of its 5 distinct chip areas fall between 40,936 and 40,982. That is 81 to 127 µm² below the
lowest golden sample. Its lowest text, c10_v4, was cleaned into `c10_clean/max_reg.v`. The
cleaned text gives a byte-identical shipped-flow netlist, 40,936.0896 µm² and 1,393 cells. It
passes lint, EQY (PASS) and the contract (17/17 ok).

## Harden of c10_clean (mirror `/Users/samuelzhang/ttharden/mr_c10v4`, evidence in `harden_c10_clean/`)

| Metric | Baseline | c10_clean | Cosmetic harden noise (ra_n03 / ra_n04) |
|---|---:|---:|---:|
| Std-cell area µm² | 46,819.2 | **47,073.9 (+254.7)** | 46,990.5 / 47,220.9 |
| Utilization | 90.09% | 90.58% | |
| Std-cell instances | 1,942 | 1,920 | |
| Setup WNS ss (max/nom/min) ns | 41.79 / 43.31 / 44.43 | 40.23 / 41.41 / 42.38 | 38.21 / 42.90 (worst) |
| Setup WNS tt (max/nom/min) ns | 70.72 / 71.55 / 72.23 | 70.50 / 71.08 / 71.56 | |
| Setup WNS ff (max/nom/min) ns | 76.06 / 76.13 / 76.18 | 76.08 / 76.18 / 76.26 | |
| Hold WNS ss (max/nom/min) ns | 1.136 / 1.147 / 1.156 | 1.184 / 1.192 / 1.199 | |
| Hold WNS tt (max/nom/min) ns | 0.415 / 0.420 / 0.425 | 0.435 / 0.439 / 0.443 | |
| Hold WNS ff (max/nom/min) ns | 0.109 / 0.112 / 0.115 | 0.121 / 0.123 / 0.125 | |
| Setup / hold violations | 0 / 0 | 0 / 0 | |
| Max slew / cap / fanout | 381 / 1 / 11 | **269 / 1 / 11** (inside 260–381 / 1–2 / 11–13) | 316/2/13, 260/1/11 |
| Power (metrics `power__total`) | 3.050 mW | **3.365 mW (+10.3%)** | 2.971 / 3.220 |
| Power, nom_tt report: seq / comb / clock | 1.114 / 0.967 / 0.389 mW | 1.143 / **1.197** / 0.389 mW | comb 0.920 / 1.069 |
| Route DRC, antenna, Magic DRC, illegal overlap | 0, 0, 0, 0 | 0, 0, 0, 0 | |
| LVS | clean | clean (0) | |
| Wirelength µm | 53,890 | 51,111 | |

Where the area changed, by cell class (`pnl` netlists): logic −149.3, buf +241.5, clkbuf
+74.6, dly (hold) +140.5, clkinv −52.7, ff +4.4. Synthesis keeps the logic saving, but the
resizer and hold repair add more than that back.

The extra combinational power (+24% versus base, +12% versus the worst noise sample) fits a
21-deep ripple. In this design S changes on nearly every SCORE clock, so the comparator toggles
continuously whether or not `en` is set, and a ripple has more internal transitions than ABC's
original structure. That inference comes from the vectorless STA activity model and was not
measured with real switching activity.

**Decision:** rejected. Std-cell area is worse than the baseline and no better than the
cosmetic-rewrite harden noise. Setup WNS is 1.57 ns worse. Power is outside the noise samples.

## Considered, not pursued
- **Sharing the compare with the mac adder.** In the pass-1 `score_done` cycle the 22-bit adder
  result is unused (`load` overrides S), so it could compute S − M. This would need:
  - new mac_unit ports (a borrow output) and a 22-bit operand mux (`~M` versus `term`, about
    22 × 28.5 µm²) on the adder's b input;
  - a 23rd bit for the signed borrow.

  That changes the max_reg and mac_unit interfaces, which the brief forbids. It probably costs
  more than the ~600 µm² of compare logic it replaces. Defer to the mac_unit or controller
  phase if wanted.
- **`sdffq_1` (scan flop as enable mux).** It is 83.4 µm², against 92.2 µm² for dffq plus mux,
  so it would save about 8.8 µm² per bit. Yosys and LibreLane do not infer it, and
  instantiating library cells in RTL breaks the RTL contract and simulation flow.
- **Clock gating:** out of scope (the contract rejects it).

## Takeaways for later modules
- `synth_area.py` module numbers move by about 300 µm² for a pure operand swap (n06). Do not use
  them as evidence.
- Shipped-flow synthesis has a noise band about 290 µm² wide for golden rewrites, and up to
  +800 for candidate rewrites. Use paired variants and the in-context cone split (`cone.py`) to
  attribute a delta.
- Harden noise, about 400 µm² across 3 samples, is larger than synthesis noise. Any gain under
  roughly 400 µm² (about 1% of the chip) cannot be confirmed at harden level with one run.
