# Integration log

## 1. Restore template documentation

Restored `README.md`, `docs/info.md`, and `test/README.md` from the repository's initial Tiny Tapeout template commit, `2b4a337`. A path-scoped Git diff confirmed all three files match that commit. Local commit `8940828`.

## 2. Reduce the area of the integrated top

The `6121eb1` baseline mapped to 52,899.9296 µm² using Yosys 0.46 and ABC with the pinned GF180 7-track TT/3.30 V Liberty views. The 346.64 × 160.72 µm die has 55,711.9808 µm² before core margins and physical support cells.

The wrapper and controller each stored the same query. The top now holds one query bank until completion and the standalone controller still latches its input by default. The controller reloads the complete operand row before using it. The divider shares its subtractor with the rounding comparison and initializes private datapath registers when accepting a request. The output encoding and 20-cycle divider latency are unchanged.

Files changed are `src/project.v`, `src/attention_controller.sv`, and `src/divider.v`. The complete mapped design reports zero Yosys check problems and occupies 47,304.3648 µm². The integrated pin test, 1,088,022 divider vectors, and all seven Verilator controller configurations passed. Top-level Verilator lint completed with the existing filename and mixed reset warnings plus unused subtractor bits. The next iteration reduces the extra buffer registers and checks physical fit.
