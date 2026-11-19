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
