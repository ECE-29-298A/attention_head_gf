# exp_lut: architectural area optimization (Agent 3, provisional)

Date: 2026-11-26. Verdict: **original RTL retained.** `opt/best/exp_lut.v` is byte-identical to
`snapshot/exp_lut.v` (SHA-256 `873546cc…`). All results are provisional: the frozen contract
does not exist yet. `verif/` and `review/` were not read.

Eleven candidate formulations were tried, plus 8 to 11 cosmetic variants of each (138 texts in
total: 12 base texts, 126 variants). Every one is EQY-proven equivalent to the golden at REGISTERED=0 and REGISTERED=1 and
passes the existing block test. None reduces the in-context exp_lut cone robustly:
- Several candidates are 300 to 570 µm² smaller standalone.
- In the chip, flattened ABC re-merges their logic. The golden's in-context cone (2,447.6 µm²) is
  already near the bottom of its own noise distribution.
- The few chip-level wins come from ABC reshuffling the rest of the chip, not from exp_lut.

## Method
- **Candidates.** `make_cands.py` writes `candidates/`. It replaces only the weight logic (golden
  lines 55–109). The header, port list, REGISTERED generate block and handshake stay
  byte-identical. Tables are generated from `round(255·e^(−k/4))` and asserted equal to the
  golden literals.
- **Variants.** `make_variants.py` applies the same 11 function-preserving rewrites to the golden
  (noise band) and to every candidate (spread). Output goes to `variants/`. The rewrites:
  - v1: invert the mux select;
  - v2: reverse the order of the case items;
  - v3: `||`/`&&` become `|`/`&`;
  - v4 to v6: combinations of v1 to v3;
  - v7: reverse the OR-term order;
  - v8: write `always @*`;
  - v9: rotate the OR terms by one;
  - v10: invert the if/else;
  - v11: write `|x` as `x != 0`.
- **`verify.sh`** runs three checks:
  - Verilator `-Wall` lint at REGISTERED 0 and 1.
  - EQY against `snapshot/exp_lut.v` (`eqy_R0.eqy`, `eqy_R1.eqy`: SAT, depth 1, no assumptions,
    cutpoints or black boxes). R0 is purely combinational. R1 has the same `W_r`/`done_r` encoding
    on both sides, so depth 1 is a full induction step. `memory_map` lowers the ROM that `proc`
    infers from the case table, which is an exact lowering.
  - The unmodified `test/blocks/test_exp_lut.py` and Makefile, copied to a space-free temp dir with
    `SRC_DIR` pointing at the candidate.
- **EQY negative controls** (`negctl/`):
  - x01: one table entry wrong;
  - x02: truncation instead of rounding;
  - x03: one overflow term dropped.

  All three **FAIL**, as required.
- **Name collisions.** EQY matches internal nets by name. A candidate that reuses a golden name
  for a different function gives a false FAIL: c05's first `out_of_range` failed this way and the
  net was renamed. Candidates use distinct internal names where the meaning differs.
- **Area:**
  - `area_eval.sh` runs `synth_area.py` (default ABC, exploration only).
  - `ll_mod.sh` is a module-level shipped flow: LibreLane Yosys.Synthesis with the project config,
    `DESIGN_NAME exp_lut`, REGISTERED=0. It reproduces the AREA 2 script and `no_synth.cells`
    (which excludes `mux2_1`, so muxes cost 32.9 µm² as `mux2_2`).
  - `ship.sh` runs **`scripts/ll_synth.sh`**, the judge, on a full copy of `original_rtl` with only
    `exp_lut.v` replaced. It runs one job at a time and waits while any Docker container is
    running.
- **`cone.py`.** exp_lut has no flops and its W nets are not named after flattening, so the cone is
  built forward from its inputs. It starts from the S-register Q nets
  (`core.exponent_unit.D[*]`) and `config_chain[7:4]`, and finds the cells that are pure functions
  of them. It keeps those that depend on `shift`, plus the D-only cells whose every load is inside
  that set. The result is `exp`; `rest = chip − exp`. Cells that merge W into the mac x-mux or the
  L adder land in `rest`.
- **Records.** `collect.py` writes `runs/collected.json`; `build_attempts.py` writes `attempts.json`.

## Noise band (shipped flow, golden rewrites)

| Source | Distinct chip areas µm² |
|---|---|
| exp_lut golden rewrites (12 texts) | 41,116.1 (×10: base, v1–v6, v8, v10, v11), 41,127.1 (v9), **41,375.1 (v7)** |
| max_reg golden rewrites (prior) | 41,063.4, 41,076.6, 41,116.1, 41,197.3, 41,348.8, 41,351.0 |

- **Combined band: [41,063.4, 41,375.1], i.e. −52.7 / +259.0 around the base.**
- The exp_lut rewrites widen the top end by 24.1 µm². v7, a pure reordering of the OR terms, adds
  +259 µm², of which +239 is inside the exp cone.
- **In-context exp_lut noise with exp_lut itself unchanged.** `cone.py` was run on the 71 max_reg
  netlists, 42 of them distinct. The exp cone ranges 2,375.2–2,757.2 µm² (mean 2,581.7,
  σ 101.2). Golden base: 2,447.6 µm², 96 cells.

## Context range (why no context-only candidate)
W is observed only in VALUE, where `D = M − S_t`.
- M is unreset. With `cont = 1` before a fresh run it holds power-up garbage, so D can take any
  22-bit value.
- Even after a fresh run, the flash data is a free input. Pass-2 rows need not match pass 1, so
  D ∈ [−2,088,960, 2,088,960], which includes every D[21] = 1 pattern.
- `score_shift` takes all 16 values.

The only unreachable values are the 16,383 D values in [2,088,961, 2,105,343]. That gives no
useful don't-care, so every candidate is standalone-equivalent.

## Attempts
All 138 texts pass lint (pass-static), EQY R0 and R1 (proven) and the block test (pass-sampled).
Δ is chip area against the golden base, 41,116.1 µm². "exp" is the in-context cone (golden
2,447.6 µm²). Ranges cover all variants of a family.

| # | Formulation | synth_area µm² | ll_mod (module) µm² | chip µm², min / median / max | exp in context, min / median / max | Decision |
|---|---|---:|---:|---|---|---|
| golden | log shifter, 5-bit increment, 25-entry case, zeroing | 2,414.7 | 2,318–2,683 | 41,116.1 / 41,116.1 / 41,375.1 | 2,447.6 / 2,447.6 / 2,686.9 | **retained** |
| c01 | fold the rounding into a 6-bit table | 2,296.2 | 2,380–2,450 | 41,430.0 / 41,498.1 / 41,498.1 | 2,836 / 2,891 / 2,891 | rejected, +314 to +382 |
| c02 | overflow saturates the index (5 ORs) | 2,432.3 | 2,544–2,676 | 41,179.8 / 41,179.8 / 41,673.7 | 2,678 / 2,678 / 2,867 | rejected |
| c03 | fold + saturate the window to 63 | 2,311.5 | 2,340–2,538 | 41,142.4 / 41,563.9 / 41,563.9 | 2,557 / 2,577 / 2,762 | rejected |
| c04 | radix-4 shifter | 2,315.9 | 2,421–2,553 | **40,999.8** / 40,999.8 / 41,566.1 | 2,551 / 2,775 / 2,891 | rejected: the −116 comes from the rest of the chip; the exp cone is +327 |
| c05 | radix-4 + fold | 2,452.0 | 2,452–2,568 | 41,296.1 / 41,847.1 / 41,847.1 | 2,621 / 3,056 / 3,056 | rejected |
| c06 | fold, ungrouped case | 2,296.2 | 2,380–2,450 | same netlists as c01 | same as c01 | rejected |
| c07 | D>>s window plus staged round-bit mux | 2,357.6 | 2,347–2,672 | 41,021.7 / 41,700.0 / 41,700.0 | 2,377 / 2,812 / 2,933 | rejected: the single low sample is v7; the other 11 texts are +305 to +584 |
| c08 | overflow don't-care OR-merge (15 muxes become `hi \| !s&lo`) | 2,291.8 | **2,114**–2,685 | 41,254.4 / 42,046.9 / 42,046.9 | 2,630 / 2,672 / 2,672 | rejected: smallest standalone (−568 against the golden ll_mod); chip +931 (rest +707) |
| c09 | OR-merge + fold | 2,774.7 | 2,498–2,742 | 41,478.3 (all texts) | 2,737 | rejected |
| c10 | OR-merge + fold + 3-OR saturation (index ≥ 49) | 2,583.8 | 2,241–2,371 | **40,971.2** / 41,133.7 / 41,133.7 | 2,439 / 2,467 / 2,467 | best family; rejected (see below) |
| c11 | fold + 3-OR saturation | 2,305.0 | 2,303–2,415 | 41,135.9 / 41,278.5 / 41,278.5 | 2,432 / 2,432 / 2,571 | rejected |

### Paired variants (same rewrite on golden and candidate; Δ chip against that golden variant)

| Rewrite class | golden chip | c04 | c07 | c08 | c10 | c11 |
|---|---:|---:|---:|---:|---:|---:|
| base, v1–v6, v8, v10, v11 | 41,116.1 | −116 / +66 | +305 to +584 | +931 | **+17.6** | +162 |
| v7 (OR order reversed) | 41,375.1 | +191 | −353 | −121 | −404 | −239 |
| v9 (OR order rotated) | 41,127.1 | +147 | +573 | +920 | −114 | +9 |

The v7 golden sample is the band's unlucky high point, so the v7 column flatters every
candidate. Against the golden base (41,116.1), c10_v7 is −144.9 and c10_v9 is −103.2.

### Why c10 is not adopted
- **Dominant class.** 9 of its 11 texts give the same netlist, at +17.6 µm² chip and +19.8 µm² exp
  against the golden. That is noise.
- **Low samples.** c10_v7 (40,971.2) is 92 µm² below the band's lower end. Its exp cone is
  2,456.4 µm², +8.8 against the golden, so the entire −144.9 is rest-of-chip ABC reshuffle (rest
  38,514.8 against 38,668.4). That is the same pattern as max_reg c04, which was rejected. c10_v9 is
  the same: exp −8.7, rest −94.3.
- **No exp-cone gain.** c10's best exp cone, 2,438.9 µm², is 8.7 µm² below the golden. There is no
  in-context exp_lut gain to carry into D7 cluster placement. The total is far below the about
  400 µm² that a harden could confirm (max_reg takeaway), so no harden was justified, and D7 rules
  out per-module hardens anyway.

## Observations for later work
- Standalone and in-context results disagree in both directions:
  - golden: 2,683 standalone (`ll_mod`), 2,448 in context;
  - c08: 2,114 standalone, 2,672 in context.

  In context the chip-wide `fx`/`mfs`/`&dch` run re-merges the OR-merged shifter back into
  `mux2_2`/`mux4` (c08: 13 `mux2_2` + 8 `mux4` in context, against 6 + 4 standalone).
- Sub-block costs (native Yosys, exploration):
  - 6-bit window shifter: about 1,020 µm²;
  - overflow detection: about 235;
  - 5-bit table: about 630;
  - increment plus gating: about 430;
  - the folded 6-bit table: about 910 (saves about 120 standalone).

  The OR-merge don't-care cuts the shifter-plus-overflow block from 1,256 to 1,056. These are real
  structural savings that ABC does not keep at chip level.
- **If D7 cluster synthesis ever keeps a boundary around exp_lut**, for example a separate ABC run
  per cluster, re-evaluate c08 and c10. c08 is −568 µm² and c10 −312 µm² against the golden in
  the module-level shipped flow. A `(* keep *)` boundary on the shifter/table nets was probed at
  module level only (`explore/`, ±300 µm² noise, inconclusive) and not pursued: it is a synthesis
  directive whose effect depends on ABC.
- **Sharing with the controller.** `score_shift` is static config, and W feeds only the mac x-mux
  and the L adder, so there is no logic left to share. Precomputing shift decodes would need flops
  (about 64 µm² each).
- **Timing.** Nothing is adopted, so there is no WNS impact. The shifter is a 4-level mux plus a
  table on a 100 ns clock.

## Files
- **Kept in git:** `candidates/`, `variants/`, `negctl/`, `explore/` (sub-block probes, the AREA 2
  script copy and `msynth.sh`), `shipped_flow/*.txt|*.stat.json|*.cone.json`,
  `shipped_flow/module/*.stat.json`, `attempts.json`, `best/exp_lut.v`, and the scripts named
  above.
- **Git-ignored:** `runs/`, which holds the RTL copies, verification logs and EQY partitions, and
  `*.nl.v` netlists.
- **Shipped-flow run dirs:** `/Users/samuelzhang/ttharden/llsynth/el_*` and `elmod_*`.
