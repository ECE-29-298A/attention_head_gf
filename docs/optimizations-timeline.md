# Optimization timeline

Checked against git history (`git log --all`), `INTEGRATION_LOG.md`, `pd_flow/PROGRESS.md` and the local Claude Code session logs from Nov 3 to 26. Authors: **Eugene** = `say-no-to-sleep`, **Samuel** = `Saahmuael`, **Felix** = Felix Deng.

The tile percentages don't all use the same denominator, so compare µm² values:
- Nov 12–13 used the template's rough figure, 340 × 160 = 54,400 µm².
- From Nov 19 on, the real 1×1 die is 55,712 µm² and the placement core is 51,967 µm².

## Timeline

| Date | Who | Commit | Optimization | Measured effect |
|---|---|---|---|---|
| Nov 3 | Felix | `3d3a713` | Controller cut from 3 steps to 2 passes. Pass 1: K → score → max. Pass 2: score → LUT weight → × V → accumulate. | Structural change; no area figure recorded |
| Nov 3 | Eugene | `8a403f5` | Exact `e^(-D/2)` lookup table replaces the 2^(−23Δ/32) approximation | Accuracy fix; no area figure |
| Nov 12 | Eugene | `0c2433a` | All multiplies done by shift-and-add on ripple adders (no CLA/CSA) in `accum` and `score_mac` | 57,793 → 41,292 µm²: **106% → 75.9%** of tile |
| Nov 12 | Eugene | `bbf309c` | Controller shrink: 16-cycle shift-add sequencing, duplicate score/weight/output registers removed, address and byte registers removed, 5-bit count replaced by a 4-bit last index | 41,292 → 36,642 µm²: **≈67%** on the 54,400 base (65.8% on the real die; the commit message says 65%) |
| Nov 13 | Eugene | `79cd511` | INT4 → INT8 (a cost, not an optimization) | 36,633 → 48,020 µm²: **67% → 88%** |
| Nov 13 | Eugene | `79cd511` | `accum`: reset/clear removed (the first token loads instead of adds). O0–O3 form a ring rotating every clock, replacing 80 hold muxes and the 4:1 read mux. Python model parameterized (d, n_max) | `accum` 15,193 → 10,866 µm²: **88% → 78.8%** |
| Nov 19 | Samuel | `1ee182f` | Wrapper and controller share one query register. Divider shares its subtractor with the rounding compare | 52,900 → 47,304 µm² (−10.6%) |
| Nov 19 | Samuel | `702fc88` | Operand row rotated through its low byte instead of a mux. Divider reads the stable L directly. Read adapter exposes the SPI byte directly | → 44,736 µm² (−15.4% from 52,900). First routed 1×1 fit: 49,515 µm² |
| Nov 19 | Eugene | `64ada15`, `1085757` | SmolLM accuracy: per-column V scales (host only), 0.25-nat LUT steps (13 → 25 entries), 4 extra output bits (12-bit output) | Median error vs float **11.7% → 5.0%** (host-computed scores) |
| Nov 19 | Eugene | `d10a2ed` | Full 64-dim Q·K scores with 4-wide outputs, instead of d=64 everywhere (that would need ≈1,700 more flops). Host-set score shift with round-to-nearest | Next-token agreement with float **92.8% → 96.3%**. Cost: +19% generic cells |
| Nov 19 | Felix | `70bfb3f` | `exp_lut` uses a staged mux shifter that keeps only the bits it needs, instead of add-then-full-barrel-shift | No number recorded. The two Nov 19 widening commits together reached 51,813 µm² |
| Nov 19 | Eugene | `84749cf` (branch `deslop-area`, **not merged**) | Plumbing audit (DESLOP): 1-bit SPI, 22 → 8 states, combinational LUT, load-on-first-input | 54,608 → 45,131 µm². Felix redid the same ideas on main (next row) |
| Nov 25 | Felix | `c459cd9` | Q read from flash 1 byte at a time (32-bit Q register removed). M preloaded so the LUT's 23-bit subtractor is removed. `score_mac` + `accum` merged into one `mac_unit` sharing one adder. `max_reg` loads the first score. Unreachable divider checks removed | 51,813 → 43,548 µm² (−16%), 355 → 299 flops |
| Nov 25 | Felix | `164fa84` | Synthesis strategy `DELAY 4` → `AREA 2`, max fanout 10 → 20 | ≈53,780 → 42,280 µm² (estimate) |
| Nov 25 | Felix | `c810362` | 2 outputs per run instead of 4. Lighter design repair (10% slew/cap margins, no input buffers) | 42,280 → 37,926 µm² (−10.3%), 299 → 242 flops |
| Nov 25 | Eugene | `4348176` | **Tape read (1 of 3):** host writes Q/K/V in consumption order. One flash read, no addresses, K and V never stored, pass 1 once per head | **12× faster** (13.5M → 1.1M clk per head), 242 → 204 flops |
| Nov 26 | Samuel | `03de4ac` | **Quad SPI read (2 of 3):** `0x6B`, 4 bits per flash clock, so the adder never idles | **2×** (1.1M → 0.55M clk per head) |
| Nov 26 | Samuel | `03de4ac` | **8 outputs per run (3 of 3):** ring of 8 sums, V stored by bit plane. A head takes 8 runs instead of 32 | **≈3.5×** (→ 0.16–0.17M clk). Area cost +122 flops; 90.1% core utilization |
| Nov 26 | Samuel | `03de4ac` | SPI target host interface replaces the 8-bit parallel bus | 35,040 → 34,522 µm² |
| Nov 26 | Samuel | `197bb55` | PD flow config (F1) | 46,819 → 45,476 µm² (−2.87%) |
| Nov 26 | Samuel | `56af306` | Allow `mux2_1` (PDK exclusion was a false positive) (F2) | → 44,912 µm² (−564) |
| Nov 26 | Samuel | `802a821` | Datapath cluster hand placement ("tetris") | 44,907 µm², 86.6% packing |
| Nov 26 | Samuel | `5b8369e` | Divider c06: 4 always-zero dividend bits not stored, quotient stored pre-complemented (no 12 XORs), FSM state merged into the step counter. EQY-proven equivalent | 44,911.6 → 44,777.7 µm² at signoff (synthesis estimate −367) |
| Nov 26 | Samuel | `d201f4d` | mac_unit c09: multiplicand inverted before the shift with the sign fill done by a shift, and L = first ? W : L+W as a mux after the adder. EQY-proven at OUTPUTS 8/4/2 | With c06: **43,429.8 µm²** at signoff (−7.2% vs the 46,819 baseline) |
| Nov 26 | Samuel | `0ddbc6a` | Whole-chip hand placement (ga1) replaces the per-cluster placement | 43,394.7 µm² (only −35.1; density converges at ≈84%) |
| Nov 26 | Samuel | `9871e2c` | Controller a11 (**provisional**: contract and review pending) | 43,151.0 µm² (−278.8) |
| Nov 26 | Samuel | `7ac5c95` | F3: max fanout 16 + max wire length 300, so signoff has zero max-cap violations (a cost, not a saving) | 43,295.9 µm² (+144.9) |
| Nov 26 | Samuel | `3acc3da`, `7ae0b05` | Rejected: clock gating g1/g2, which was smaller in synthesis but bigger after the clock tree | +897.9 / +1,016 µm² |

Physical design since the Nov 26 baseline (46,819 µm², 90.1% core): latest signoff **43,295.9 µm²** with zero cap violations (−7.5%). The −278.8 from controller a11 is still provisional.

Overall speed at N = 16 and 10 MHz: **13.5M → ≈0.16M clocks per head, 1.35 s → ≈17 ms (≈80–85×).**

## Slide corrections

- **"106% → 75.8%" (ripple):** correct. It is 57,793 → 41,292 µm² on the 54,400 base.
- **Controller "67%":** correct on the 54,400 base. On the real die it is 65.8%, which is the 65% in the commit message.
- **INT4 → INT8 "67% → 83%": wrong.** The Nov 13 synthesis measured **88.3%** (48,020 µm²). Then "accum → 78%" is correct (78.8%).
- **"26 entries":** the RTL has 25 non-zero entries (D' = 0..24). Everything at 25 or above gives 0, so 26 only counts the zero.
- **"11% → 5%":** correct as median relative error (11.7% → 5.0%), with scores computed on the host.
- **"120%" (dimension slide):** no measurement in the repo or logs gives 120%. The recorded figures are +19% generic cells (`d10a2ed`) and 51,813 µm² = 93% of the die / 16% over the routed design. Use one of those.
