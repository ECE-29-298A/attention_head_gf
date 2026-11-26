# Integration log

## 1. Restore template documentation

Restored `README.md`, `docs/info.md`, and `test/README.md` from the repository's initial Tiny Tapeout template commit, `2b4a337`. A path-scoped Git diff confirmed all three files match that commit. Local commit `8940828`.

## 2. Reduce the area of the integrated top

The `6121eb1` baseline mapped to 52,899.9296 µm² using Yosys 0.46 and ABC with the pinned GF180 7-track TT/3.30 V Liberty views. The 346.64 × 160.72 µm die has 55,711.9808 µm² before core margins and physical support cells.

The wrapper and controller each stored the same query. The top now holds one query bank until completion and the standalone controller still latches its input by default. The controller reloads the complete operand row before using it. The divider shares its subtractor with the rounding comparison and initializes private datapath registers when accepting a request. The output encoding and 20-cycle divider latency are unchanged.

Files changed are `src/project.v`, `src/attention_controller.sv`, and `src/divider.v`. The complete mapped design reports zero Yosys check problems and occupies 47,304.3648 µm². The integrated pin test, 1,088,022 divider vectors, and all seven Verilator controller configurations passed. Top-level Verilator lint completed with the existing filename and mixed reset warnings plus unused subtractor bits. The next iteration reduces the extra buffer registers and checks physical fit.

Commit `1ee182f` records the first RTL reduction.

## 3. Remove redundant datapath buffers

The controller now rotates the loaded operand row through its low byte during arithmetic, replacing an operand selection mux. It keeps the weight sum stable through division, so the integrated divider can use it directly. The standalone divider still captures its denominator and preserves its handshake. The read adapter exposes the completed byte from the SPI engine while response-valid is high, with one request outstanding.

Files changed are `src/attention_controller.sv`, `src/divider.v`, and `src/Memaccess/qspi_read_adapter.v`. Area fell to 44,735.9808 µm², a 15.43% reduction from baseline. Yosys reported zero mapped design check problems. The top, divider, controller, and SPI regressions passed. The pin-level test completed in 27,680 cycles on RTL and on the mapped and routed netlists using functional models from the pinned Liberty.

The GF180 1×1 trial placed and routed through Metal4. OpenROAD reported 48,310 µm² with tap, tie, clock, and hold repair cells, about 93% of the placement core. There were zero router and antenna violations, zero unrouted multi-terminal signals, and both power grids passed the shape connectivity check. OpenRCX exposed negative setup slack at 40 ns. At 100 ns with 1 ns input transition and 10 fF output load the same trial had 24.464 ns setup slack and -0.074 ns hold slack, with electrical violations still to repair. The next iteration checks a routed candidate with targeted buffering and a larger hold margin.

Commit `702fc88` records the second RTL reduction.

## 4. Reproduce the single tile build and characterize the routed design

The default project timing target is now 100 ns (10 MHz) and the placement density target is 92%. Extracted timing demonstrated a setup failure at 40 ns, so the previous 20 ns project default was too aggressive. The Tiny Tapeout author field remains blank. Its three template Markdown files remain byte identical to the initial commit. The pin protocol is available in [docs/pin-protocol.md](docs/pin-protocol.md).

### Synthesis and physical evidence

| Run | Area | Result |
| --- | ---: | --- |
| Integrated baseline `6121eb1` | 52,899.9296 µm² | 95.0% of the 55,711.9808 µm² tile die before physical support |
| Query and divider optimization `1ee182f` | 47,304.3648 µm² | 10.58% lower mapped area than baseline |
| Final RTL `702fc88` | 44,735.9808 µm² | 15.43% lower mapped area than baseline |
| Local routed timing candidate | 49,515 µm² | 95% core utilization, 88.9% of die area, including physical support and timing repair |

OpenROAD used the Tiny Tapeout 1×1 pin DEF and the GF180D 5LM/11K technology LEF. All 43 signal pin geometries matched the template. The routed candidate had zero detailed router violations, zero unrouted multi-terminal signals, zero antenna violations, and connected VDD/VSS shapes. Signal routing stayed within Metal4. The router and connectivity checks use the local OpenROAD flow.

OpenRCX min/nom/max rules were paired with FF/TT/SS Liberty respectively for extracted STA. With a 100 ns clock, 0.25 ns uncertainty, maximum I/O delays of 4 ns, minimum I/O delays of zero, 1 ns input transition and 10 fF output load, worst setup slack was **+29.177 ns** and worst hold slack was **+0.144 ns**. One driver exceeded the capacitance limit by about 0.03 pF and the same net exceeded its slew limit by 2.13 ns. The chosen routed netlist passed the zero-delay pin-level Cocotb test in 27,680 cycles. The setup and hold figures apply to the stated constraints.

The configured shuttle LibreLane run, GDS stream-out, shuttle precheck, and full DRC/LVS remain open. Power and actual flash board timing were outside these local measurements.

### Reproduce

The local runner requires native Yosys with ABC, OpenROAD for placement and routing, PyYAML, and initialized GF180 library submodules. The PDK gitlink is `25ed9c64`, with 7-track cells at `43beb45e`. Measurements used Yosys `0.46` and OpenROAD `edf00dff`.

```sh
python3 scripts/gf180_one_tile.py
python3 scripts/gf180_one_tile.py --tile-def /path/to/tt_block_1x1_pgvdd.def --clock-period 40
```

The second command reproduces the initial physical fit trial. Its placement uses the measured 92% density and the given clock period for estimated checks. Supply `--rcx-rules` with the nominal, minimum, and maximum GF180D extraction files named `rcx-nom.rules`, `rcx-min.rules`, and `rcx-max.rules` to extract and check that run. The driver returns a nonzero status if the extracted report contains timing or electrical violations. The measured post-route repair sequence, routed layout, logs, exact pin DEF, and OpenRCX rule bytes are archived locally under `build/gf180_fit_evidence/`.

With Verilog cell models and a mapped or routed netlist, the same pin-level test can be run with:

```sh
python3 test/top/run.py --netlist /path/to/routed.v --cell-models /path/to/cells.v
```

The tile dimensions and library selection are defined in [Tiny Tapeout’s GF180D tile table](https://github.com/TinyTapeout/tt-support-tools/blob/main/tech/gf180mcuD/tile_sizes.yaml) and [technology configuration](https://github.com/TinyTapeout/tt-support-tools/blob/main/tech.py). The extracted reports use the [Open PDKs GF180D rules](https://github.com/fossi-foundation/open-pdks/tree/main/gf180mcu/librelane).

Commit `fca4997` records the reproducible flow and selected local layout. Full regression checks also passed for all four arithmetic blocks, both SPI byte widths, both controller simulators, the standalone divider, and the Python model.

## 5. Check a final electrical repair

Upsizing the remaining overloaded XOR and rerouting kept the die, pins, router, antenna, connectivity, and gate simulation checks passing. Area rose to 49,528 µm². Extraction showed that the original driver recovered, but a downstream net then exceeded its capacitance and slew limits. Setup margin fell from +29.177 ns to +14.478 ns. The 49,515 µm² candidate remains the selected result. The trial logs are under `build/gf180_fit_evidence/last-trial/`.

The one-tile area objective is met in the local GF180 checked route. Next physical work is electrical closure in the shuttle's processed PDK flow, followed by GDS checks.

## 6. Recover the one-tile area after the 64-dim score change

Commits `d10a2ed` and `70bfb3f` widened the score datapath and added the rounded LUT shift. The mapped area rose to 51,813.3056 µm² with 355 flip-flops, 16% above the 44,729 µm² design that routed in one tile. Measurements use the same Yosys/ABC flow and pinned 7-track TT/3.30 V Liberty as section 2.

- Scores read one Q byte and one K byte per dimension into the existing operand register, so the 32-bit query register and its 4:1 mux are removed. Flash traffic is unchanged at 128 single-byte reads per score.
- Pass 2 preloads the score with M and subtracts, so `exp_lut` receives D = M − S and its 23-bit subtractor is removed. `exp_lut` is combinational in the core (`REGISTERED=0`), because D and shift stay stable through accumulation.
- `mac_unit` replaces `score_mac` and `accum`. The two never run in the same cycle, so they share one 22-bit adder and shifter, and the O ring bypasses the adder while scoring.
- The read adapter uses the controller's stable address (`LATCH_ADDR=0`). The SPI engine is single-lane only (`X1_ONLY=1`).
- `max_reg` loads the first score directly, with no reset or sentinel. `last` is derived from the held token count. The integrated divider omits the invalid and overflow checks, which cannot trigger in this design (`CHECK_INVALID=0`), and rounds and negates with a single incrementer.

The mapped area is 43,548.3776 µm² with 299 flip-flops: 15.95% below HEAD and 2.64% below the design that routed in one tile. The top, controller (seven configurations and the cocotb tests), block, divider, SPI and Python regressions pass. A Yosys gate netlist passes the top test. The shuttle LibreLane run is still to be confirmed in CI.

## 7. Select an area synthesis strategy for the shuttle flow

The first shuttle LibreLane run of section 6 failed in `OpenROAD.RepairDesignPostGPL`. Global placement warned that the 92% target density was below the design's utilization (GPL-0302). Design repair then added 12.8% area (168 buffers and 77 resized cells for 103 slew and 33 fanout violations), and detailed placement failed (DPL-0036).

LibreLane defaults `SYNTH_STRATEGY` to `DELAY 4`, and the Tiny Tapeout configuration does not override it. With LibreLane's ABC command sequences reproduced in Yosys on the pinned TT Liberty, the section 6 RTL maps to:

| Strategy | Mapped area | Nets with fanout > 10 |
| --- | ---: | ---: |
| `DELAY 4` (default) | 53,780 µm² | 28 |
| `AREA 3` | 47,557 µm² | 9 |
| `AREA 0` | 42,422 µm² | 29 |
| `AREA 2` | 42,280 µm² | 29 |

These reproductions omit LibreLane's SDC-driven ABC constraints, so they are estimates. `DELAY 4` exceeds the roughly 52,000 µm² placement core before repair. `src/config.json` now selects `AREA 2` and raises `MAX_FANOUT_CONSTRAINT` from 10 to 20. The 100 ns clock leaves ample setup margin, and repair still enforces the Liberty slew and capacitance limits.

## 8. Two outputs per run and lighter design repair

With `AREA 2` the shuttle run passed design repair but failed detailed placement during clock tree synthesis (DPL-0036). The placement core is 39 rows × 339.92 µm (51,967 µm²). OpenROAD reported these cell areas:

| After | Area | Core used |
| --- | ---: | ---: |
| Design repair (112 buffers, 105 resized, 12 input buffers) | 49,837.63 µm² | 95.9% |
| Clock tree synthesis (24 clock buffers, 6 clock inverters) | 51,321.58 µm² | 98.8% |

The 299 flip-flops occupied 19,190.44 µm² of that area.

Each run now returns two V components instead of four. The accumulator ring keeps two 20-bit sums, the V operand buffer holds two bytes, and the phase and output index are one bit each. `chunk` widens to 0–31 and selects components `2*chunk` and `2*chunk+1`. Its top bit is bit 5 of the count byte, `{2'b00, chunk[4], N}`, and a count byte with bit 7 or 6 set is refused. A run sends four result bytes and reads two V bytes per token. A full 64-component head takes 32 runs. Each output value is computed exactly as before.

`src/config.json` also sets `DESIGN_REPAIR_MAX_SLEW_PCT` and `DESIGN_REPAIR_MAX_CAP_PCT` to 10 (default 20) and disables input port buffering, which removes 12 `dlyb_1` cells (421.48 µm²). Signoff still fails on any remaining slew or capacitance violation.

The design has 242 flip-flops (−57). The `AREA 2` reproduction of section 7 maps it to 37,926.47 µm², down from 42,279.55 µm² (−10.3%). Yosys default ABC maps it to 39,252.37 µm². The top, controller (seven configurations, 91 cases, and the cocotb tests), block, divider, SPI and Python regressions pass, as does the Yosys gate netlist. The shuttle run is still to be confirmed in CI.

## 9. Read the memory as a tape

Each byte used to be its own flash transaction: 40 SPI bits for 8 bits of data, then 8 MAC cycles. Every chunk run also repeated pass 1, although the maximum is the same for all 32 chunks of a query.

The host now writes the memory in the order the chip consumes it (`tape()` in `python/src/attention_model.py`; layout in `docs/pin-protocol.md`). The controller issues one `0x03` read at address 0 and only clocks after that, so it has no address logic and no byte handshake. K and V bits go to the shift-add MAC as they arrive, MSB first, so neither is stored; only the current Q byte is held. `mac_unit` loads the accumulator on bit 7, the first bit to arrive, instead of bit 0. The config byte is `{cont, 3'b000, shift}`: `cont = 1` keeps the flash read open and the maximum, and computes the next chunk without pass 1. The count byte is `N` alone again; the chunk number is gone from the chip because the tape decides which V bytes a run sees.

`attention_controller.sv` drives the flash pins directly. `qspi_read_adapter`, `qspi_byte` and `spi_multi_io_byte` are no longer in `info.yaml`; their sources and `test/spi_byte` are unchanged. `test/controller/cocotb` tested the removed memory handshake and is deleted.

| | Before | After |
| --- | ---: | ---: |
| Flip-flops | 242 | 204 |
| Generic cells (Yosys `synth`, `abc -g cmos2`) | 2,574 | 2,308 |
| Clock cycles, one run at N = 16 | 423,407 | 66,222 |
| Clock cycles, each continue run at N = 16 | – | about 33,400 |
| Clock cycles, 32 chunks of one head at N = 16 | about 13.5 M | about 1.1 M |

The cycle counts come from the pin-level test, which stalls each result byte for three cycles. The GF180 Liberty area was not measured here because the PDK submodule was not checked out; the cell and flip-flop counts above use the same Yosys 0.69 on both designs. The cost is memory: a 32-chunk head at N = 16 is 68,608 tape bytes instead of 2,112, and the host must reset the chip to release chip select before rewriting it.

The top (four tests, including a real SmolLM head and four-chunk heads), controller (79 cases with a full 32-chunk head, reset in nine phases, three host-ready schedules), block, divider and Python regressions pass. The top test also passes on a Yosys generic gate netlist. The shuttle LibreLane run is still to be confirmed in CI.

## 10. SPI target host interface

The 8-bit parallel host bus (`ui_in`, `uo_out` and the `uio[6]`/`uio[7]` handshake) is replaced by an SPI target in mode 0: SCK, MOSI and CS# on `ui_in[2:0]`, MISO on `uo_out[0]` and DRDY on `uo_out[1]`. `uio[7:6]` are now unused; the flash pins are unchanged. A 16-bit config frame `0000000, cont, shift[3:0], N-1[3:0]` starts a run on its CS# rise. Each component is then read as a 16-bit frame, the signed 12-bit result followed by 4 zeros, while DRDY is high. Frames, timing rules and reset length are in `docs/pin-protocol.md`; `config_frame()` and `decode_result_frame()` are in `python/src/attention_model.py`.

- `project.v`: SCK and CS# go through 2 synchronizer flops and 1 edge flop each. MOSI has no synchronizer: the chain takes `ui_in[1]` directly, 2 to 3 clk after the SCK pin rises (including late metastability resolution). The host holds MOSI from 4 clk before the rise to 4 clk after it, so no flop samples MOSI while it changes. The config registers are one 9-bit chain `{cont, shift, last}` that shifts only while the core is idle, which ignores a config write while busy. One synchronized CS# rise drives both `start` and `out_ready`. The `stage` FSM, the LAUNCH cycle, the 1 to 16 range check, `cfg_ready`/`cfg_accept` and the `uo_out` gating are removed. None of the new flops is reset.
- `attention_controller.sv`: takes `last = N-1`, so the decrementer is gone. `high_byte` and the byte mux are also removed. OUTPUT ends on one `out_ready` per component. `out_bit` is the divider's `result[11]`, and `out_shift` (a synchronized SCK fall with CS# low) shifts it while `out_valid` is high. The gate is needed: the divider writes `result` one clk before OUTPUT, and an ungated shift in that cycle loses the MSB. The controller test found this.
- `divider.v`: a `shift` input moves `result` left and takes in 0. A completing division overrides it. A port was used instead of the planned `SHIFT_OUT` parameter: `test/divider` changes by one declaration either way, and the parameter would add a generate branch. The `result` reset stays, because removing it saves at most 31 µm².

| | Before | After |
| --- | ---: | ---: |
| Flip-flops | 204 | 204 |
| Cell area (§6 recipe: Yosys 0.71 `synth`, default ABC, GF180 7-track TT) | 35,040 µm² | 34,522 µm² |
| top / controller / divider | 1,646 / 5,639 / 8,460 µm² | 1,297 / 5,084 / 8,765 µm² |

`max_reg` RTL is unchanged but maps 81 µm² larger, which is ABC variation. The LibreLane harden is still to be run.

Timing: the chip acts on an SCK or CS# edge within 3 clk, and every host rule is 4 clk, leaving 1 clk for metastability and pad delays. In zero-delay RTL simulation, host phases of 3 clk still pass and 2 clk fail.

Tests:
- The top test drives SPI frames on timers unrelated to clk: exactly 4-clk phases (SCK = clk/8), the same with every edge on a clk edge, jittered non-integer 4 to 7 clk phases, and fixed 10.37-clk phases.
- It reads DRDY exactly `t_CSW` = 4 clk after each read and asserts it is low.
- In random runs it sends a config frame while busy and checks that the frame is ignored. It also puts junk on the unused `ui_in` bits, sends 0 to 2 SCK pulses with CS# high before each read, and holds reset for exactly 3 clk.
- `tb_controller.sv` reads results bit by bit at a random pace. Outside OUTPUT it sends random shifts and CS# rises.

All regressions pass: Python, divider (now with shift checks), controller (79 cases, 3 seeds), the top test (runner and TT Makefile), blocks and spi_byte. The top test also passes on a flattened Yosys generic gate netlist; with a 2-clk reset that netlist goes to X, so the 3-clk minimum is real. Verilator lint shows the same 3 warnings as before.

## 11. Quad SPI read of the tape

The tape is now read with Fast Read Quad Output (`0x6B`) on the Tiny Tapeout QSPI Pmod pins: `uio[0]` CS0#, `uio[1]` IO0, `uio[2]` IO1, `uio[3]` SCK, `uio[4]` IO2, `uio[5]` IO3. `uio[6]` and `uio[7]` (the Pmod RAMs' CS1#/CS2#, which have no pull-ups) are driven high. IO0 is an output only for the command and address; IO1 to IO3 are always inputs. The W25Q128JV-IQ has QE set at the factory, so the chip sends no setup command. Host-side behaviour is unchanged.

- `attention_controller.sv`:
  - `rx_bit` becomes a 4-bit `nibble`, loaded from IO3..IO0 on each SCK rise and shifted up one bit per clock; the MAC takes `nibble[3]`, so the 4 bits are used on the 4 clocks after the rise (1 bit per clock, the adder's rate). SCK runs at `clk`/4 and is high for 1 clock (`spi_sck <= rise`). The next rise comes with the nibble's last bit.
  - `pos` now increments every clock (no enable). The command, address and 8 dummy clocks reuse CMD with `pos` as a clock count: RESTART is pos 0, CMD runs pos 1 to 161, SCK rises from phase 1 and IO0 changes in phase 0, and the 41st rise takes the first data nibble on the edge into SCORE. `spi_mosi` decodes `0x6B` from `pos`; `spi_mosi_oe = CMD && !pos[7]` drops after the last address bit, 8 SCK cycles before the flash drives IO0.
  - No stalls: RESTART + CMD (162 clk), a score row (1024) and a V block (16) are all even, and `pos` is cleared only at start and where its parity is kept, so `pos[0]` always equals the ring phase. The `component` flop is removed and `pos[0]` drives the MAC's `sel` and the divider phase wait.
  - The last nibble of a run has no rise after it, so the flash keeps the next nibble on IO3..IO0. A continue run's start edge samples it. The flash therefore sees exactly `40 + 2·bytes` rises, with nothing read ahead.
- `tape()`: each token's two V values are stored by bit plane (`v_pair()`: `a7 b7 a6 b6 … a0 b0`), so at 1 bit per clock each bit reaches the ring head when its component is there. Q and K bytes are unchanged.
- `project.v`: pin map and output enables only.

| | Before (§10) | After |
| --- | ---: | ---: |
| Flip-flops | 204 | 206 (+4 nibble, −1 `rx_bit`, −1 `component`) |
| Cell area, §10 recipe | 34,522 µm² | 34,904 µm² |
| controller | 5,084 µm², 37 flops | 5,466 µm², 39 flops |
| Clock cycles, start to first division, fresh run at N = 16 | 66,144 to 66,145 | 33,186 |
| Same, continue run at N = 16 | 33,311 to 33,312 | 16,640 |
| Clock cycles, 32-chunk head at N = 16 (plus about 51 per run for the divisions) | about 1.10 M | about 0.55 M |
| Top test, 4-chunk head at N = 16 (with host frames) | 168,759 | 85,785 |
| Controller test, total cycles (seed 298) | 5,112,363 | 2,582,246 |

The run counts were probed in the controller test. A fresh run is exactly 162 + 2064·N clocks to the first division, and a continue run 1040·N. Because the nibble shifts every clock, the capture register needs only 3 mux2s, against a 4:1 lane mux, 4 load enables and the stall rule in a first version (35,112 µm², 207 flops). With this recipe, ABC moves the controller's area by about ±100 µm² for single-gate edits, so variants inside that range were chosen on gate count. `spi_mosi_oe` has a sub-ns static hazard at the CMD→SCORE edge. It is harmless: IO0 is 0 on both sides, and the flash does not drive until 8 SCK cycles later. Registering the output enable would cost a flop.

Tests: both flash models are now `0x6B` quad flashes. They check the command and address, start driving after the 8th dummy clock, change data after each SCK falling edge (the top model used to change after the rising edge), and put junk on undriven lines. They fail if IO0 is driven while the flash drives it, if IO0 is driven outside the command and address (including while deselected), or if IO0 is not driven during the command. The top test also checks that IO1 to IO3 are inputs and that CS1#/CS2# are driven high, and adds resets during the dummy clocks and just after the first data nibble. The controller test adds a reset during the dummy clocks. The bit-count assertions are now `40 + 2·bytes`. Both models also check IO0 setup and hold around each command rise (IO0 must equal its value from the previous clk) and mode 0 (SCK low while CS# is high and when CS# falls). Mutations caught: 7 dummy clocks, IO0 released late, IO0 output enable on IO1, CS2# low, IO2/IO3 swapped, a different V bit order, a read-ahead at the end of a run, IO0 decoded from `pos - 2` (changing on the edge that raises SCK), and the continue-run start rise also firing in fresh runs (an SCK pulse in RESTART). All regressions pass (Python 10, divider, controller 79 cases × 3 seeds, top runner and TT Makefile 3 pass + 1 skip, blocks, spi_byte), and Verilator lint shows the same 3 warnings.

## 12. Eight outputs per run

The output ring depth is now the parameter `OUTPUTS` (2, 4 or 8) on `tt_um_attention_head_gf`, `attention_controller` and `mac_unit`; the chip uses 8. A run computes 8 output sums on the one shared adder, so a head is 8 runs instead of 32. Each run ends with 8 divisions and 8 result frames (same frame and DRDY rules as §10); after the eighth CS# rise the chip is idle.

- `mac_unit.v`: the ring is one `20·OUTPUTS`-bit register that shifts by 20 every clock; the head `O0 = ring[19:0]` is the only output, and only the tail entry has a mux (sum, or the head while scoring). No enables, no reset. `sel` is `log2(OUTPUTS)` bits; L updates at `sel == 0`.
- `attention_controller.sv`: the ring phase is `pos[P-1:0]` (P = log2 OUTPUTS). VALUE is `8·OUTPUTS` clocks with `pos = {bit[2:0], component[P-1:0]}`, `bit_sel = ~pos[P+2:P]` and end at `&pos[P+2:0]`; there is still no stall logic. `output_index` is P bits; OUTPUT increments it and goes idle after index `OUTPUTS-1`. `o1` is gone.
- Ring phase: from the first V bit of a run to its last division, `pos` only counts up or wraps at multiples of OUTPUTS (score row 1024, V block 8·OUTPUTS). The clears at start and at the end of CMD (162 clk, not a multiple of 4 or 8) all come before the run's first V bit, which loads every ring entry afresh (`first`, bit 7), so no alignment is needed there and nothing was added for it.
- `tape(Q, K, V, chunks, outputs=8)`: each token's V values for a chunk are `v_planes()` bytes in bit-plane order `c0b7 c1b7 … c(n-1)b7 c0b6 … c(n-1)b0`; a head has `64/OUTPUTS` chunks. `v_pair()` is replaced by `v_planes()`.

Area (§6 recipe, Yosys 0.71, default ABC; `chparam -set OUTPUTS n tt_um_attention_head_gf`):

| | Before (§11) | OUTPUTS = 2 | 4 | 8 |
| --- | ---: | ---: | ---: | ---: |
| Cell area | 34,904 µm² | 34,912 | 37,867 | 42,899 |
| Flip-flops | 206 | 206 | 247 | 328 |
| mac_unit (local) | 10,260 / 74 | 10,238 / 74 | 12,906 / 114 | 18,009 / 194 |
| controller | 5,466 / 39 | 5,501 / 39 | 5,789 / 40 | 5,672 / 41 |
| Final cell area estimate (× 38,493 / 35,040) | 38,343 | 38,352 | 41,598 | 47,125 |
| Core utilization estimate (51,967 µm²) | 73.8% | 73.8% | 80.0% | 90.7% |

At 8 the change is +122 flops: +120 ring (6 × 20) and +2 `output_index`; mac logic grows only 132 µm² beyond the flops. Other modules are unchanged RTL (divider moves 40 µm² by ABC). The estimate scales our synthesis number by the baseline's LibreLane final / our-recipe ratio (38,493 / 35,040 = 1.099), not by LibreLane's own synthesis ratio (38,493 / 33,121 = 1.162), since the two synthesis flows differ. 90.7% is close to the 96 to 99% at which placement failed before; 4 outputs (80%) is the standard-cell fallback.

Cycles per head at N = 16 (tape clocks `162 + 1024·N + (64/OUTPUTS)·N·(1024 + 8·OUTPUTS)`, plus 64 divisions of about 25 clk and at most OUTPUTS−1 phase wait each; host frame time not included): OUTPUTS = 2 about 0.551 M, 4 about 0.289 M, 8 about 0.158 M. A continue run at 8 is 17,408 clk and a fresh run 33,954 to the first division. The top test's 4-chunk N = 16 head took 85,938 / 88,862 / 94,888 cycles at 2 / 4 / 8 including host frames (4 runs each, so 8, 16 or 32 reads).

Tests: `test/controller/run.py` now runs OUTPUTS = 8, 4, 2 (`--outputs` to pick; Verilator `-GOUTPUTS`); `test/top/run.py --outputs 2|4|8` (default 8; the TT Makefile flow uses the top's default 8); `OUTPUTS=n make mac_unit` in `test/blocks` (default 8). Directed controller cases run the chunk(s) that hold their 4 values, so at 8 they are single fresh runs; random cases and a whole head still cover continue runs. Top tests take chunk numbers modulo `64/OUTPUTS`, and after each run's last read check that DRDY stays low for 40 clk. The mac block test checks the ring head every cycle. At OUTPUTS = 2 the controller test's cycle count (seed 298) equals §11's 2,582,246. Mutations caught at 8: V bits read byte-wise (`bit_sel = ~pos[2:0]`), the division phase off by one, and 7 reads per run instead of 8.
