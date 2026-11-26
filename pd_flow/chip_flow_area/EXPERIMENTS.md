# Chip-level PD area experiment (user decision D6: minimize area)

Scope: shipped chip `tt_um_attention_head_gf`, golden RTL, physical-design and flow settings only.
No change to `src/`, `tt/`, the PDK or the reference project.
Each run is a space-free copy `/Users/samuelzhang/ttharden/fx_<tag>` of the golden mirror. Only
the copy's `src/config.json` is changed (`scripts/run_fx.sh`).

Full hardens use `source ~/ttsetup/env.sh; python tt/tt_tool.py --pdk gf180mcuD --harden`.
**3 of 5 were used, one at a time.**

## Result

**Best legal configuration: h2 (`recommended_config.patch`).**

| | Std-cell area |
|---|---|
| Baseline | 46,819.2 µm² |
| h2 | **45,475.8 µm²** |
| Saving | **−1,343.4 µm² (−2.87%)** |

That is 35% of the about 3,800 µm² of PD-addressable overhead.

h2 at signoff:
- every corner: setup WNS ≥ +41.79 ns, hold WNS ≥ +0.058 ns;
- slew/cap/fanout 281/2/6, inside the D2 band 260–381 / 1–2 / 11–13 (fanout is below it);
- DRC, LVS and antenna 0; power 2.934 mW (baseline 3.050 mW, −3.8%).

Hold-safer alternative: h3 (`alt_holdsafe_config.patch`). It is the same configuration except that it keeps the `clkbuf_16`
CTS root.

| | Std-cell area | ff hold WNS |
|---|---|---|
| h3 | 45,633.8 µm² (−1,185.4) | +0.076 ns |

## Where the overhead is made (baseline, from per-step `state_out.json`)

| Step | Std-cell area after the step | Change |
|---|---:|---:|
| Floorplan (synthesis netlist) | 41,116.1 | |
| Tap/endcap insertion | 42,986.4 | +1,870.3 tap/endcap |
| **RepairDesignPostGPL** | 45,291.4 | **+2,305.0**: repair buffers +1,154.7, logic upsizing +1,067, flop upsizing +57, buffer +26 |
| **CTS** | 46,819.2 | **+1,527.9**: 3 × clkbuf_16, 16 × clkbuf_8 sinks, 14 dummy loads (285 µm²) |
| ResizerTimingPostCTS onward | 46,819.2 | 0 (no setup or hold buffers, no diodes) |

Setup and hold repair margins (`PL_/GRT_RESIZER_*_SLACK_MARGIN`) therefore add no area and are not area levers.
Post-GRT repair is off in the TT config.

The overhead comes from:
- `repair_design` slew/fanout repair;
- TritonCTS buffer choice.

Mechanism found (`scripts/slew_attr.py`): fanout repair (limit 20) inserts the **weakest buffer in the library**,
each driving 21 loads.
- Baseline: 12 × `dlyb_1` (35.1 µm² each, REVIEW N3).
- 8 of those nets carry **142 of the 381** ss slew violations, at up to 8.56 ns.
- With `dly*` excluded, the resizer picks `buf_1` (same weak drive, same slew).
- With `buf_1`/`clkbuf_1` also excluded, it picks `buf_2`. In h1 those nets still carry 201 of 425 violations.
- With `buf_2`/`clkbuf_2` also excluded, it picks `buf_3`. The fanout-buffer nets drop to 42 of 281 violations.

## Variables (checked against LibreLane 3.0.14 source in the image)

- **`EXTRA_EXCLUDED_CELLS`** (`config/flow.py`). Deprecated names: `RSZ_DONT_USE_CELLS`, `DONT_USE_CELLS`.
  - Wildcards excluded from synthesis **and** PnR. In PnR they go through `set_dont_use` (`common/io.tcl`), so they
    affect repair_design, CTS and repair_timing.
  - In synthesis they are removed from the ABC liberty. The synthesized netlist hash is checked for every run;
    it stayed `a339bf99…`, bit-identical to the baseline.
- **`DESIGN_REPAIR_MAX_SLEW_PCT` / `_CAP_PCT`**: `repair_design -slew_margin/-cap_margin` (`repair_design.tcl`).
  - Only the slew margin moves area: p6 ≡ p4, and p7 = control.
- **`CTS_CLK_BUFFERS`, `CTS_ROOT_BUFFER`, `CTS_SINK_CLUSTERING_SIZE`, `CTS_SINK_CLUSTERING_MAX_DIAMETER`,
  `CTS_SINK_BUFFER_MAX_CAP_DERATE_PCT`**: `clock_tree_synthesis -buf_list/-root_buf/-sink_clustering_size/
  -sink_clustering_max_diameter/-sink_buffer_max_cap_derate` (`cts.tcl`).
- **Not settable:** `repair_design -buffer_gain` / `-max_utilization` are read from env in `repair_design.tcl` but are not
  declared step variables. Only declared variables reach the step.
- **Not exposed:** CTS `-dont_use_dummy_load`. The dummy loads cannot be turned off from config.
- **`PL_TARGET_DENSITY_PCT`**: gpl `-density`.

## Method and evidence levels

1. **Partial runs** (`run_fx.sh <tag> <ovr> OpenROAD.STAMidPNR-3`, about 45 s).
   - The flow stops after antenna repair (step 43). Area at that point equals final area (see the table above).
   - The control `p0_control` is bit-identical to the baseline through CTS and resizer timing.
   - For the 3 configurations later hardened in full, the post-CTS netlists of the partial and full runs are
     bit-identical (k4 = h1 `985b2886…`, k6 = h2 `be11968f…`, k8 = h3 `6fdbfeae…`). The partial-run areas are
     therefore exact and reproducible.
2. **Post-GRT multi-corner STA proxy** (`scripts/sta_proxy.sh`).
   - Re-runs LibreLane's own `OpenROAD.STAMidPNR` step standalone on the step-43 input at max_ss, max_tt and max_ff
     (global-routing parasitics).
   - Step 43's own ss/ff metrics are stale carry-overs from pre-PnR STA, so they are not used.
   - Calibration on the baseline: proxy ss slew 170 vs signoff 381; proxy ff hold +0.131 vs signoff +0.109.
   - **The proxy is only a ranking signal.** It predicted k4 under the baseline (122 < 170), but signoff gave 425.
3. **Full hardens**: signoff RCX STA at all 9 corners, Magic DRC, Netgen LVS, antenna.

## Experiments

Deltas are std-cell µm² against the baseline, split by origin group (`scripts/census.py`, instance-name based; it
reproduces the metrics classes exactly):
- **cts** = `clkbuf_*`/`clkload*` instances;
- **repair** = `fanout*`/`load_slew*`/`wire*`;
- **logic** = synthesis cells after resizing.

Proxy columns: ss slew count, ff hold WNS (control 170 / +0.131).

| Tag | Knob(s) | Δ total | Δ cts | Δ repair | Δ logic | Proxy ss slew | Proxy ff hold | Decision |
|---|---|---:|---:|---:|---:|---:|---:|---|
| p0_control | none | 0 | 0 | 0 | 0 | 170 | +0.131 | harness bit-identical to baseline |
| p1_nodly | exclude `dly*` | −250.2 | −39.5 | −210.7 | 0 | 168 | +0.139 | keep; `dlyb_1` → `buf_1` 1:1, slew unchanged |
| p5_nodly_nox1 | + exclude `buf_1`, `clkbuf_1` | −346.8 | −39.5 | −316.1 | +8.8 | 64 | +0.137 | keep |
| p2_cts_small | CTS bufs {2,4}, root 8 | +307.4 | +307.3 | 0 | 0 | 174 | +0.120 | reject (54 smaller buffers) |
| p3_cts_derate100 | CTS sink max-cap derate 100% | +483.0 | +482.9 | 0 | 0 | 177 | +0.130 | reject (65 × clkbuf_2) |
| c1_root8 | CTS root clkbuf_8 | −158.0 | −158.1 | 0 | 0 | 170 | +0.118 | partial lever |
| **c2_cl20_buf4** | CTS bufs {clkbuf_4}, root 8, cluster 20, diameter 80 | **−680.5** | −680.5 | 0 | 0 | 174 | +0.130 | **keep** |
| c3_cl20_d80 | cluster 20 / diameter 80 alone | +4.4 | +4.4 | 0 | 0 | 170 | +0.134 | no effect |
| c4_cl20_buf2 | as c2 with clkbuf_2 sinks | −882.4 | −882.5 | 0 | 0 | 166 | +0.101 | reject: lowest hold margin, not hardened |
| c5_cl20_buf4_root4 | as c2 with root clkbuf_4 | −759.5 | −759.5 | 0 | 0 | 166 | +0.118 | not hardened (hold) |
| p4_margin0 | slew and cap margin 0 | −588.3 | 0 | −193.2 | −395.1 | 274 | +0.136 | slew cost; combine only |
| p6_slew0 | slew margin 0 | −588.3 | 0 | −193.2 | −395.1 | 274 | +0.136 | identical to p4 |
| p7_cap0 | cap margin 0 | 0.0 | 0 | 0 | 0 | 170 | +0.131 | no effect |
| d96 | density 96% | +81.2 | −13.2 | +8.8 | +85.6 | 150 | +0.129 | reject |
| k3_x_c2 | p5 + c2 | −1,009.8 | −702.5 | −316.1 | +8.8 | 66 | +0.124 | fallback |
| k4_x_c2_s0 | p5 + c2 + slew 0 | −1,431.2 | −658.6 | −377.6 | −395.1 | 122 | +0.124 | → h1 |
| k5_x_c2_s5 | p5 + c2 + slew 5 | −1,082.2 | −671.7 | −250.3 | −160.2 | 77 | +0.129 | dominated |
| k6_x2_c2_s0 | p5 + exclude `buf_2`, `clkbuf_2` + c2 + slew 0 | −1,343.4 | −676.1 | −298.5 | −368.8 | 38 | +0.119 | → **h2** |
| k7_x2_c2 | as k6 with slew 10 | −860.5 | −680.5 | −215.1 | +35.1 | 28 | +0.126 | dominated |
| k8_x2_c2r16_s0 | as k6 with root clkbuf_16 | −1,185.4 | −518.1 | −298.5 | −368.8 | 44 | +0.129 | → h3 |

## Full hardens (signoff)

Run paths:
- baseline: `/Users/samuelzhang/ttharden/attention_head_gf/runs/wokwi`;
- h1: `/Users/samuelzhang/ttharden/fx_h1_k4/runs/wokwi`;
- h2: `/Users/samuelzhang/ttharden/fx_h2_k6/runs/wokwi`;
- h3: `/Users/samuelzhang/ttharden/fx_h3_k8/runs/wokwi`.

Copies (metrics, final netlist, configs, per-corner `checks.rpt`, CTS and repair logs) are in `runs/<tag>/`.

### Std-cell area by metrics class (µm²)

| Class | baseline | h1 (k4) | **h2 (k6)** | h3 (k8) |
|---|---:|---:|---:|---:|
| Sequential | 21,001.5 | 20,986.1 | 20,986.1 | 20,986.1 |
| Combinational | 20,237.5 | 19,857.8 | 19,857.8 | 19,857.8 |
| Inverter | 763.9 | 763.9 | 763.9 | 763.9 |
| Buffer (synthesis) | 105.4 | 105.4 | 131.7 | 131.7 |
| Clock buffer | 1,352.2 | 785.9 | 755.1 | 913.2 |
| Clock inverter (dummy loads) | 175.6 | 83.4 | 96.6 | 96.6 |
| Timing-repair buffer | 1,154.7 | 777.1 | 856.1 | 856.1 |
| Tap and endcap | 1,870.3 | 1,870.3 | 1,870.3 | 1,870.3 |
| Tie | 158.1 | 158.1 | 158.1 | 158.1 |
| **Std-cell total** | **46,819.2** | **45,388.0** | **45,475.8** | **45,633.8** |
| Δ | | −1,431.2 | **−1,343.4** | −1,185.4 |
| Cells | 1,942 | 1,924 | 1,924 | 1,924 |
| Utilization | 90.09% | 87.34% | 87.51% | 87.81% |

### Timing, legality and signoff

| | baseline | h1 (k4) | **h2 (k6)** | h3 (k8) |
|---|---|---|---|---|
| Setup WNS ns, ss max/nom/min | 41.79 / 43.31 / 44.43 | 41.90 / 43.14 / 44.16 | 41.79 / 43.06 / 44.09 | 41.36 / 42.72 / 43.81 |
| Setup WNS ns, tt max/nom/min | 70.72 / 71.55 / 72.23 | 71.27 / 71.89 / 72.41 | 71.20 / 71.83 / 72.36 | 71.01 / 71.68 / 72.23 |
| Setup WNS ns, ff max/nom/min | 76.06 / 76.13 / 76.18 | 75.88 / 75.96 / 76.03 | 75.97 / 76.05 / 76.11 | 76.05 / 76.11 / 76.17 |
| Hold WNS ns, ss max/nom/min | 1.136 / 1.147 / 1.156 | 1.006 / 1.030 / 1.054 | 0.974 / 1.004 / 1.032 | 1.031 / 1.054 / 1.076 |
| Hold WNS ns, tt max/nom/min | 0.415 / 0.420 / 0.425 | 0.340 / 0.355 / 0.369 | 0.325 / 0.342 / 0.358 | 0.355 / 0.368 / 0.381 |
| **Hold WNS ns, ff max/nom/min** | 0.109 / 0.112 / 0.115 | 0.065 / 0.075 / 0.082 | **0.058** / 0.068 / 0.078 | 0.076 / 0.084 / 0.092 |
| Setup/hold violations | 0/0 | 0/0 | 0/0 | 0/0 |
| Max slew, ss max/nom/min | 381 / 301 / 251 | **425** / 359 / 288 | 281 / 189 / 128 | 264 / 187 / 135 |
| Max slew, tt (each) | 117 | 0 | 0 | 0 |
| Max slew, ff (each) | 0 | 0 | 0 | 0 |
| Slew/cap/fanout (worst) | 381/1/11 | **425**/2/6 | 281/2/6 | 264/2/6 |
| In D2 band (≤ 381/2/13)? | yes | **no (slew)** | yes | yes |
| Power, tt | 3.050 mW | 2.926 mW | 2.934 mW | 2.960 mW |
| Routed wirelength | 53,890 µm | 50,057 µm | 50,554 µm | 50,988 µm |
| Route DRC / Magic DRC / illegal overlap | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |
| LVS errors | 0 | 0 | 0 | 0 |
| Antenna nets / route antenna | 0/0 | 0/0 | 0/0 | 0/0 |
| Setup / hold buffers inserted | 0/0 | 0/0 | 0/0 | 0/0 |
| Synthesis netlist sha256 | a339bf99… | same | same | same |
| Die, ports, LEF pins, disconnected pins (9) | — | same | same | same |
| Decision | ref | **reject (slew band)** | **recommend** | hold-safer alternative |

### Attribution of h2's −1,343.5 µm², by master against the baseline final netlist

- **CTS −676.1 µm²**
  - Sinks and trunk: 16 clkbuf_8 sinks and 3 clkbuf_16 are replaced by 17 clkbuf_4 sinks and 3 clkbuf_8 (root/trunk).
  - Dummy loads: 14 → 11 (CTS-0207). 7 clkinv_1, 1 clkinv_4, 1 inv_2 and 2 clkbuf_4 replace 3 clkinv_4, 4 inv_3,
    3 inv_2, 1 clkbuf_2 and 3 clkbuf_4.
  - 17 clusters of ≤ 20 sinks replace 16 of 21–24 sinks. That is also why the clock-leaf fanout violations
    fall from 11 to 6.
- **Repair −298.5 µm²**
  - The 12 `dlyb_1` (−421.5) and the clkbuf_1/2/4 and buf_1/2 repair buffers are replaced by buf_3 ×21, buf_4 ×7,
    buf_8, clkbuf_3 and clkbuf_4 ×3.
  - 33 repair buffers, against 49 in the baseline.
- **Logic −368.8 µm²**
  - Less driver upsizing under slew margin 0: oai32_4 −2, nor4_4, dffq_4, mux4_2, xor3_2, nand3_4, aoi21_4, … go
    back to their _1/_2 sizes.
  - Synthesis buffer class +26.3: the 6 synthesis buffers are sized up from buf_2, which is now dont-use.
- Every component is large against the about 400 µm² harden noise band (CTS alone −676) and traced to its knob by
  master counts.
- The flow is deterministic. Each partial screen and its full harden produced the bit-identical post-CTS netlist,
  so the numbers are reproducible.
- Effect of the `buf_2` exclusion (h1 → h2): +87.8 µm² and −144 ss slew violations.

## Risks

1. **Hold margin falls at ff, −40 °C** from +0.109 to +0.058 ns (h2) or +0.076 ns (h3).
   - The cause is the weaker clkbuf_4 sink buffers and clkbuf_8 root/trunk: tt/ff clock latency and skew rise.
   - It is met at all 9 corners, but it is thinner. The noise of hold WNS across RTL rewrites is not characterized.
   - Post-CTS hold repair (margin 0.1 ns) did not trigger, because placement-estimated hold slack stayed above it.
     If a future netlist goes negative at signoff, there is no post-GRT hold repair in the TT flow
     (`RUN_POST_GRT_RESIZER_TIMING` off).
   - Use h3 if more hold margin is wanted. It costs +158 µm².
2. **Slew margin 0** means repair_design aims at the 3 ns limit using placement-estimated parasitics.
   - In h1 the result went out of band (425). h2 sits inside the band only because the stronger fanout buffers
     removed about 144 violations.
   - The count is sensitive. Re-check the D2 band on any RTL or netlist change. h2's margin to the ceiling is 100
     violations (h3: 117).
3. **Cap violations at the band ceiling (2)**: fanout13/fanout14 (buf_3) at 0.211–0.222 pF against the 0.2 pF limit, at ss
   and tt (baseline: 1, `_2344_/Q`).
4. **`EXTRA_EXCLUDED_CELLS` also removes the cells from the synthesis liberty.**
   - The synthesized netlist was bit-identical in every run with this RTL.
   - A different RTL could map differently, because ABC sees a smaller library. Check the synthesis hash/area
     after RTL changes.
   - The delay cells are also unavailable to hold repair. Hold repair inserted 0 buffers in every run, but a future
     hold fix would use bufs (more area per ns).
5. The proxy STA is not a legality check. Only the full-harden numbers above are claims.
6. KLayout DRC is not run by the TT flow (`RUN_KLAYOUT_DRC: 0`), the same as the baseline. Magic DRC, LVS and antenna are clean.

## Not pursued (and why)

- **Tap distance:** PDK `FP_TAPCELL_DIST`, latch-up/well rules (DF.13/14). TT tile rules. Not touched.
- **Tie cells:** 158 µm² is the same in synthesis and after repair, so there is nothing to gain.
- **Raising `MAX_FANOUT_CONSTRAINT`, raising the slew limit, or a negative margin:** these would weaken the
  checks, not reduce area legitimately.
- **More CTS clustering than 20:** each leaf over 20 sinks is a fanout violation.
- **Post-GRT design repair:** off in the TT flow. Turning it on would add repair, not remove it.
- **`SYNTH_*` settings:** synthesis, not PD; covered by earlier phases (AREA 2).

## Files

- `recommended_config.patch`: h2 delta against `src/config.json`. Not applied. `git apply --check` passes, and it is
  semantically equal to the h2 copy's config.
- `alt_holdsafe_config.patch`: h3 delta, the same with `CTS_ROOT_BUFFER` clkbuf_16.
- `results.json`: every run, with area by class and census group, per-corner WS, violations, power, signoff,
  overrides, synthesis hash, proxy STA and deltas.
- `overrides/*.json`: the exact per-run overrides.
- `scripts/`:
  - `run_fx.sh`: copy, override and run (full or partial);
  - `sta_proxy.sh`: post-GRT multi-corner proxy;
  - `census.py`: area by master and origin;
  - `slew_attr.py`: slew violators by driving net;
  - `summarize.py`, `collect.py`, `make_patch.sh`.
- `runs/h*/`: full-harden evidence with SHA256SUMS.
- `runs/partial/*/`: post-CTS netlist, config and proxy per partial run.
