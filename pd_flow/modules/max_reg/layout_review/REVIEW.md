# max_reg Phase 3: independent review of the layout plan (Agent 5)

Date: 2026-11-26. Reviewed: `layout_plan/` (PLAN.md, tables.md, gen_placement.py, validate_placement.py, out/,
chip_runs/, names/, tools/, contract_*), the run trees `/Users/samuelzhang/ttharden/mr3_{b_m,b_ms,a_sdff}` and the
golden noise runs. Nothing in `layout_plan/`, `src/` or `verif/` was edited. Nothing was committed. No harden was
run. My own runs were the frozen contract, the generator check, the validator (on a copy of `out/`), a validator
mutation test, OpenSTA power in Docker, and my own parsers for STA reports, DEFs, Liberty and netlists. All of
them are in this directory.

## Verdict: CHANGES REQUIRED (two blocking items, both exact; no new harden needed). The recommendation itself is APPROVED.

- **Ship the golden RTL with free placement (c): APPROVED.** I checked every table number against the raw
  metrics, and none of the constrained runs improves any axis outside noise (§3).
- **B1 (blocking):** the `a_sdff` netlist drives the 22 SE pins from one `buf_4`. That is fanout 22, above the
  chip's `MAX_FANOUT_CONSTRAINT` of 20. In the chip run the resizer therefore inserted a free `dlyb_1` *inside* the
  frozen block. It drives 20 SE pins at 6.74 ns ss transition, against a 3 ns limit. The plan reports that the
  block "held". The Phase 4 block config has repair off and no fanout limit, so the standalone block would sign
  off a netlist that the chip flow does not keep.
- **B2 (blocking, text):** the timing claims are misattributed:
  - The claim "fixing M or S moves the ss critical path onto mac_unit's adder → S[21]" is wrong as a causal
    statement.
  - The adder → S[21] path is co-critical in **every golden harden**: second in base at +0.16 ns, second in n03,
    and the worst path in n04.
  - b_m's −2.65 ns is inside the golden band (38.21–42.90). It is diffuse placement perturbation of mac_unit's
    datapath: clk→Q +0.5 ns, front end +1.0 ns through a repair buffer whose master is a delay cell (`dlyb_1`,
    3.47 ns), carry chain +1.7 ns, tail −0.4 ns.
  - None of it is on a pin of the fixed M flops. The M-fed tail got faster.
  - Golden run n03 loses 2.27 ns on the same path with no constraint, partly through a 7.27 ns `dlyb_1`.
  - This is the same kind of error as ripple_add round 1, where a cost was put down to the wrong cause.

## 1. What I checked independently, and the results

| # | Area | Method (mine) | Result |
|---|---|---|---|
| 1 | Table numbers | `scrape_metrics.py`, `tables_check.log`: each tables.md row parsed and compared field by field with the raw `final/metrics.json` | **6 rows × 12 fields match**. Copies in `chip_runs/*/harden/metrics.json` are byte-identical to `ttharden/mr3_*/runs/wokwi/final/metrics.json`. The brief's table (46,819.2/41.79/381/1/11/3.050 … 48,151.7/34.44/418/2/11/3.545) is correct. All runs: 0 setup/hold violations, route DRC, Magic DRC, LVS and antenna 0 |
| 2 | (b) netlist identity | sha256 of `06-yosys-synthesis/*.nl.v` | baseline harden, `llsynth/base`, `mr3_b_m` and `mr3_b_ms` are all `a339bf99…`: **byte-identical**. `resolved.json` differs from baseline only in mirror paths and `MACRO_PLACEMENT_CFG`. The b_* deltas are placement and repair effects of an identical netlist |
| 3 | Critical path | `pathclass.py` (worst slack per endpoint class, flops identified by Q net), `pathcmp.py`/`pathseg.py` (stage by stage), `netpos.py` | §2 B2: the path is real and placement-induced, but it was already co-critical in every golden run. The b_m delta is diffuse displacement inside the noise band, not on the fixed flops' pins |
| 4 | a_sdff contract | `verif/run_all.sh --gate --rtl layout_plan/out/max_reg_a_sdff.v --out layout_review/contract_a_sdff` (contract hash `6d7f5b5ff9a94fc9`, 16/16 OK) | **19/19 ok**. k-induction and abc pdr proven (step, seq, power-up); 23/23 covers; vectors 558,544 cycles on Verilator and 4-state Icarus; sim_ctrl/free 10⁸ cycles; onestep 2.68·10⁸; `eqy_rtl` proven; both sanity controls fail as required. DUT sha `78a8967f…` = Agent 4's |
| 4 | Pin and arc choices | `libarcs.py` (own Liberty ss_125C_3v00 extract at 1 ns slew, 10 fF; `libarcs_ss.txt`) | Chain on A1: oai21_1 A1 ≤ A2 on both edges (rise 1.080 = 1.080, fall 0.568 < 0.633). aoi21_1 A1 is faster on rise (1.042 vs 1.149), 0.04 ns slower on fall (0.562 vs 0.524); net in favour. gt on oai21 A1 is correct. Using `sdffq_1` SE as the late select costs 1.38–1.94 ns setup, less than mux2_2 S→Z (1.77) plus dffq setup (0.95). **No arc defect. The defect is the SE fanout (B1)** |
| 4 | `no_synth.cells` | PDK file `gf180mcuD/libs.tech/openlane/gf180mcu_fd_sc_mcu7t5v0/no_synth.cells`, `SYNTH_EXCLUDED_CELL_FILE` in resolved.json | **Confirmed.** All sdff* cells are listed. Area 83.4176 × 22 = 1,835.2 µm² missing from the Yosys stat, as claimed. `mux2_1` is in `drc_exclude.cells`, as claimed |
| 4 | Upsize → DPL failure | `a_sdff_aoi222_FAILED/harden_failed/openroad-repairdesignpostgpl.log` | **Confirmed.** 30 overlaps, e.g. FIXED `b01_cmp` now `aoi222_4` overlapping `b01_ff`, then DPL-0005/0011/0033 |
| 5 | Stale check | `gen_placement.py --check` | **FRESH [] rc 0** (`rerun/gen_check.log`) |
| 5 | Validator | `validate_placement.py --out layout_review/rerun/out` (a copy, so `layout_plan/validation.json` is untouched) | **ALL_OK**, output identical to Agent 4's `validation_run.log` (`rerun/validation_run.log`) |
| 5 | Self-tests fail when their check is broken | `selftest_mutation.py`: each targeted check disabled in memory, then the self-tests rerun | **7/10 turn BAD as they should. 3/10 still pass with their own check disabled** (overlap, chain broken, chain moved off A1), because a *different* check of the same category fires (N1). `check_function` passes an equivalent A1/A2 swap and kills a first/en swap |
| 5 | Placement held in chip | `check_fixed.py`: own DEF parser over **all 16 DEFs from step 17 to final** in each run tree | b_m 22/22, b_ms 44/44, a_sdff 109/109 at each step: FIXED, exact x/y/orientation, master unchanged. Taps and endcaps identical to baseline from step 19 on. 0 overlaps with any component, including fill. Orientations row-legal. Q nets correct in the final pnl (22/22, 44/44) |
| 5 | Anchor and tap arithmetic | by hand from the cfgs | b_m site 177 ≡ 37 (mod 70), 29 sites in the [37,70) window. b_ms S at 142 ≡ 2, M at 177; the even-row tap at 175–176 falls between them. a_sdff 157 ≡ 17: taps at rel 18 (even rows) and 53 (odd rows). Block area 2,952.5 µm² recomputed from Liberty areas. All correct |
| 5 | DF.13/14 estimate | `welltie.py` on the final chip DEFs | worst 9.61 / 9.61 / 9.65 µm (Agent 4: 9.52), ≤ 15 µm. Same-row tap alone: up to 18.5 µm (b_*) and 16.8 µm (a_sdff). As in ripple_add N1, compliance rests on the tap in the well-sharing neighbour row |
| — | Name stability | own scan of the M[k] Q nets | M[0] is `_2277_` (base), `_2271_` (n03), `_2237_` (n04), `_2198_` (c10). **Confirmed unstable**; Q-net mapping is the right fix |
| — | Block power share | OpenSTA in Docker (`sta_power/`), nom_tt, nom SPEF, vectorless | a_sdff block cells (109): **76.9 µW**. Golden max_reg cone + M flops (134 cells, ctxmap definition) in base: **77.7 µW**. Base total reproduces LibreLane (2.47 mW) |

## 2. Findings

### B1 (BLOCKING): a_sdff SE fanout 22 exceeds the chip fanout limit, and the chip flow patched the frozen block

Evidence (`a_sdff_se_fanout_evidence.txt`, `chip_runs/a_sdff/harden/pnl`, `.../max_ss_125C_3v00/checks.rpt.gz`):
- `u_ld_buf` (buf_4) drives `nld_b` → 22 × `sdffq_1/SE`. `MAX_FANOUT_CONSTRAINT` is 20 in the shipped config.
- RepairDesignPostGPL (step 32) inserted `fanout1`, a **`dlyb_1`** placed free at (128.24, 98.0). Now `nld_b` drives
  b20/b21 SE plus `fanout1`, and `fanout1` drives the other 20 SE pins.
- ss result: **b00_ff..b19_ff/SE transition 6.738 ns against a 3 ns limit (−3.74 ns)**. That is 20 of the 37 slew
  violations a_sdff adds over the baseline (418 vs 381). The other 9 block pins are the S_in D/nand/nor inputs at
  3.05–3.45 ns, driven from outside the block.
- PLAN §0.4 and §6 say that with slew-legal cells "the block held" and that "explicit drivers (buf_4 on SE)" are the
  mitigation. The masters held, but the block netlist did not: a 110th cell now sits inside it. The validator's
  slew rule checks master transition at a nominal load. It does not check fanout or the actual net load.
- Phase 4 consequence: `out/a_sdff/block_librelane.json` sets `RUN_POST_GPL_DESIGN_REPAIR: false` and no
  `MAX_FANOUT_CONSTRAINT`. The standalone block would keep fanout 22 and sign it off, although the chip context never
  keeps it.

Required changes:
1. `gen_placement.build_block`: drive SE from **two** drivers with at most 11 loads each, for example two `buf_4` fed by
   `nld`, one for bits 0–10 and one for bits 11–21. There is room: the decode row uses rel sites 0–33 of 70, and a
   second buf_4 (14 sites) fits at 34–47 with no tap conflict. Keep the slew rule.
2. `validate_placement.py`: add a rule that every block-driven net has fanout ≤ `MAX_FANOUT_CONSTRAINT` (20, read
   from the shipped config). Also estimate the net transition with the actual pin load plus a wire estimate, against
   0.9 × 3 ns. Add a self-test (22-load SE) that fires this specific message.
3. Regenerate, then confirm `--check` FRESH and `validate_placement.py` ALL_OK. Rerun the gate contract into
   `contract_a_sdff/` and `contract_chip_rtl/`.
4. `block_librelane.json`: add `MAX_FANOUT_CONSTRAINT: 20`. In the PLAN §7.1 step 2 assertions, add "no repair buffer
   on any block net; block cell count = netlist cell count".
5. PLAN text:
   - §0.4 and §6: say that masters held, but repair inserted a `dlyb_1` fanout buffer into SE.
   - §2.1 and §8: the measured a_sdff numbers include this artefact (20 slew violations, plus some power and area).
     The conclusion is unchanged.

No new harden is needed, because a_sdff is not adopted for the chip.

### B2 (BLOCKING, text): the S[21] critical-path claim is misattributed

Evidence (`pathclass.log`, `s21_path_evidence.txt`, `repair_buffer_masters.txt`):

1. **The path does not move; it is a near-tie in the golden runs.** Worst ss slack by endpoint class:

   | Run | divider result | S[21] (`core.exponent_unit.D`) | mac ring | M (max_reg) |
   |---|---:|---:|---:|---:|
   | base | **41.79** | 41.95 | 45.92 | 67.56 |
   | n03 (golden) | **38.21** | 39.69 | 41.09 | 66.24 |
   | n04 (golden) | 43.85 | **42.90** | 47.76 | 65.19 |
   | b_m | 41.21 | **39.14** | 43.35 | 63.66 |
   | b_ms | 42.31 | **36.14** | 40.26 | 62.68 |
   | a_sdff | 42.64 | **34.44** | 36.40 | 69.2 (block) |

   - The S[21] path's golden range is 39.69–42.90. In n04 it is already the chip's worst path.
   - b_m (39.14) sits 0.55 ns below that 3-sample range. Its WNS (−2.65 against base) is inside the WNS band
     38.21–42.90.
   - **The b_m timing delta is not outside the noise band.**
   - max_reg's own paths keep 63–69 ns of slack in every run.
2. **Mechanism for b_m.** Same netlist. Arrival times at common pins (`pathseg.py`) split the −2.81 ns on the
   S[21] path as follows:

   | Segment | Delta | Cause |
   |---|---:|---|
   | `config_chain[7]` clk→Q | +0.5 ns | heavier load |
   | Front end, Q → `_1417_` | +1.0 ns | The worst branch switched from `_1417_/A2` to A3, through `wire11`, a **`dlyb_1`** (3.47 ns at ss). RepairDesignPostGPL inserted it on carry net `_0824_` (`_1412_` → `_1414_`), which has no buffer in the baseline |
   | 22-bit carry chain | +1.7 ns | wire |
   | Tail through the M-fed load mux (`_2051_/A1` = `core.mac.M[21]`) | **−0.38 ns** | got faster |

   - Global placement put the low adder bits 25–40 µm lower in y (`netpos.py`). The fixed M flops do not sit on the
     path and do not slow their own pins.
   - The delta is a diffuse displacement of mac_unit's datapath, of the same size as the golden n03 run (−2.27 ns on
     this path with no constraint). In n03, `fanout57`, a `dlyb_1` at **7.27 ns**, is on the path.
3. **b_ms:** −5.82 ns on the S[21] path. Q +0.6 ns; front end +1.6 ns (the same `dlyb_1` branch, `wire12`); carry
   chain **+3.6 ns**; tail −0.2 ns. This is outside the band and probably real displacement of the adder, though it
   is one sample.
4. **a_sdff:** a different netlist. Its path also carries a `dlyb_1` repair buffer (`max_cap5`, 3.67 ns).

Required changes:
1. **PLAN §0.2, §0.5, §2.4 "Timing" and §8.4:** replace "moves the ss critical path to mac_unit's adder → S[21]" and
   "which drive the new critical path". The S[21] path is co-critical in all golden hardens. Its b_m change (−2.8 ns)
   is diffuse displacement inside the noise band, comparable to golden n03, and does not run through the fixed
   flops. Only b_ms (−5.8 ns, carry chain +3.6 ns) is outside the band. Cite both `max.rpt.gz` files and n03.
2. Restate the coupling argument from facts that hold: M feeds S's load mux, S feeds the compare, and the 22 S flops
   are the adder's register. The orchestrator ruling to tetris at mac_unit bit-slice level stands on its own and does
   not need the "new critical path" claim.
3. tables.md / §0 table: add a note that b_m WNS is inside the band (the table already leaves it unbolded; the prose
   contradicts that).

### Non-blocking findings

**N1. Self-tests are category-matched, so 3 of 10 do not test their check.**
- With the overlap check disabled, "overlap" still passes through an orientation error.
- With the one-row-hop check disabled, "compare chain broken" still passes through bit-per-row.
- With the A1 test disabled, "chain input moved off A1" still passes through the hop check.

Fix: match on the specific message (e.g. `"overlap row"`, `"is not one row"`, `"not on A1"`). Evidence:
`rerun/selftest_mutation.log`.

**N2. The power attribution is wrong.** §0.3 and §2.4 attribute a_sdff's +0.30 mW combinational to "a 21-stage chain
that toggles with S every SCORE clock".
- With OpenSTA and the same vectorless method, the block's 109 cells take 76.9 µW. The golden cone + M flops take
  77.7 µW.
- So the whole chip increase is **outside** max_reg: displaced wiring (+11 mm), ABC's remapping (+549 µm²) and repair
  buffers.
- Also, vectorless activity cannot show "toggles every SCORE clock".
- Caveat: my OpenSTA chip total for a_sdff is 2.93 mW against LibreLane's 2.84 mW. The base reproduces exactly. The
  block share is unaffected. (`sta_power/`)

**N3. Flow observation for the orchestrator (outside this module): repair uses `dlyb_1` as a buffer.**
- Every harden has 12–17 `dlyb_1` among its repair buffers, about 25% of them (`repair_buffer_masters.txt`).
- Each costs 3.5–7.3 ns at ss when it lands on a path.
- This is a concrete mechanism behind the "few ns" harden setup-slack noise in the orchestrator rulings.
- Excluding the delay cells from repair buffering is a shipped-config experiment. It is not a max_reg change and
  should not be done here; whether to spend one harden on it is the orchestrator's choice.

**N4. Small wording fixes.**
- §3.2 says the names come from "the run's own synthesized netlist". `names.json` actually binds the baseline
  **final** nl (`a8286e1b…`), not the step-6 netlist (`a339bf99…`). The names are identical, but state which file.
- §3.2 says check_placed covered "step-17, DPL, CTS and final" DEFs. For b_m, `placement_check.json` has no CTS
  entry. My check of all 16 DEFs covers it.
- `b_flopcells` −68.1 µm² is 15.4 µm² *below* the lowest golden synthesis sample, not "at the lower edge" of the
  band. Either way it is not a confirmed gain.

**N5. DF.13/14** rests on the neighbour-row tap (same-row only: up to 18.5 µm). The plan states this, and Phase 4
KLayout is planned. In whole-chip tetris, keep the rule that a column must sit where the well-sharing neighbour row
has the staggered tap.

## 3. Could a constrained option win? (item 6; no harden run)

| Candidate | Assessment | Spend a harden? |
|---|---|---|
| Placement-only (a) with free masters: ABC's in-context cone fixed in bit-slice rows | The cone is 112 cells of ABC's tree compare, not bit-separable. Fixing it reintroduces the upsize/DPL hazard: ABC masters are not slew-screened, which is the aoi222 failure mode. b_m already shows that fixing just 22 flops costs +2.7 mm wire. Upper bound on benefit: all max_reg-touching wire is 5.9 mm, and the max_reg cells draw about 78 µW (about 3% of 2.47 mW). Halving the cone's internal wire (2.2 mm HPWL) saves about 1.1 mm, below the golden wire band width (1.9 mm). That is unmeasurable in one harden | **No** |
| Anchor nearer mac_unit | The chosen anchors already sit on the M/S centroid (M (99.9, 66.6), S (106.6, 68.8); b_m column x 102.5, y 27–110). The next proxy candidates are within 0.5%. The loss is the column-versus-ring shape (proxy 2,213 vs 951 µm), not the anchor | **No** |
| `b_flopcells` −68.1 µm² | Synthesis only and well below the about 400 µm² harden noise. Phase 2's c10 went −180 in synthesis to +255 in harden. Its value is stable names, not area | **No** (only if the whole-chip tetris needs stable names) |
| SE fanout fix (B1) for a_sdff | Removes about 20 slew violations and one dlyb, but cannot recover the +549 µm² synthesis loss or the +11 mm displacement | **No** |

None of them is worth a harden for max_reg. (N3 is a chip-level config question for the orchestrator.)

## 4. Phase 4 plan (PLAN §7, item 7)

**Implement `a_sdff` standalone, after the B1 fix**, as ripple_add implemented its column block although golden
ships. Reasons:
- It is the only variant that is a complete, self-contained netlist with every instance at a scripted coordinate,
  which is the D4 Phase 4 object (generate, fix, route, DRC/LVS/PEX/characterize).
- It is contract-verified (19/19, rerun here) and composes as a D5 sub-placement (70 × 23 footprint on the tap
  period, ports defined).
- `b_m`/`b_ms` are bare flop columns whose logic is ABC's unnamed in-context mapping. Standalone, they characterize
  22 dffq_1 and nothing else.
- A standalone synthesis of the golden RTL does not reproduce the in-context mapping (cone ≠ standalone ABC).

§7 is otherwise adequate (step assertions, KLayout DF.13/14 on block and chip window, Netgen + KLayout LVS,
three-corner RCX, ngspice on the critical arc, activity-annotated power). Add:
1. The B1 items: `MAX_FANOUT_CONSTRAINT` 20, the split SE spine, and the assertions "no repair buffer on a block net"
   and "cell count unchanged".
2. Recommended (cheap control): one free-placed run of the golden max_reg in the same die and pin config. It gives
   the block's area, wire and power figures a like-for-like reference. Report the block-versus-golden-cone power
   with the same `sim_ctrl` activity, since vectorless shows them equal (N2).
3. The critical arc to characterize is now S_in[0] → chain → gt → nld → 2 × buf → SE (11 loads each). Report SE
   transition against 3 ns at ss.

## 5. Required changes (summary)
1. **B1:** split the SE driver (≤ 11 loads each), add the fanout and net-transition rule plus its self-test,
   regenerate, revalidate, rerun the gate contract; fix the block config and the PLAN text.
2. **B2:** correct the S[21] critical-path attribution in PLAN §0.2, §0.5, §2.4 and §8.4 (co-critical in golden;
   b_m inside band; diffuse displacement, not on the fixed flops).
3. Recommended: N1 (specific self-test matching), N2 (power attribution), N4 (wording). N3 goes to the orchestrator.

After 1 and 2 this review would be **APPROVE**.

## Evidence index (this directory)
`metrics_scrape.{log,json}`, `tables_check.log`, `contract_a_sdff/`, `contract_a_sdff.runlog`, `libarcs.py`,
`libarcs_ss.txt`, `pathclass.{py,log,json}`, `pathcmp.py`, `pathseg.py`, `netpos.py`, `qnet.py`, `topn.py`,
`s21_path_evidence.txt`, `repair_buffer_masters.txt`, `a_sdff_se_fanout_evidence.txt`, `check_fixed.{py,log,json}`,
`welltie.{py,log,json}`, `rerun/` (gen_check.log, validation_run.log, validation.json, selftest_mutation.log/json,
out/ copy), `selftest_mutation.py`, `sta_power/` (OpenSTA scripts, logs, per-instance reports).

## Verdict: **CHANGES REQUIRED** (B1, B2). Recommendation (c), golden RTL with free placement: approved.
