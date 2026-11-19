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
