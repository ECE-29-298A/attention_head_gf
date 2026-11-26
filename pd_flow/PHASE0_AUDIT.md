# Phase 0: project audit

Branch `physical-design`, HEAD `03de4ac` (clean tree at start). Original RTL and configuration
are copied to `pd_flow/baseline/original_rtl` and `original_config` and hashed in
`pd_flow/baseline/SHA256SUMS`. That copy is the golden RTL for every EQY proof.

## Scope

The shipped design is the 7 files in `info.yaml` `source_files`. The following are not in the
build or any test of the shipped top, and are out of scope: `src/gate_adder.v` (unused
`full_adder`), `src/custom_mult.sv` (empty stub), `src/Memaccess/*` (old SPI engines; `addr_gen.v`
is empty), `benchmarks/`, `codex-reference/`.

Several docs are stale (INT4-era): `docs/blocks.md`, `docs/controller.md`, `docs/divider.md`,
`docs/int4-controller-sequence-v*.md`, `docs/integration-report.md`. The current design is
described by `src/` comments, `docs/pin-protocol.md` and `INTEGRATION_LOG.md` §9 to §12.

## Hierarchy (as instantiated) and processing order

```
tt_um_attention_head_gf #(OUTPUTS=8)          src/project.v
└── attention_controller #(OUTPUTS=8) core     src/attention_controller.sv
    ├── mac_unit #(OUTPUTS=8) mac              src/mac_unit.v
    │   ├── ripple_add #(N=22) adder
    │   └── ripple_add #(N=12) l_adder
    ├── max_reg max_unit                       src/max_reg.v
    ├── exp_lut #(REGISTERED=0)                src/exp_lut.v
    └── divider #(LATCH_DENOMINATOR=0, CHECK_INVALID=0)   src/divider.v
```

Leaf-to-root order: **1 ripple_add → 2 max_reg → 3 exp_lut → 4 divider → 5 mac_unit →
6 attention_controller → 7 tt_um_attention_head_gf.**

Parameter support to preserve: the existing regression exercises `OUTPUTS` = 2, 4, 8 (top,
controller, mac_unit), `divider` standalone at its defaults (`LATCH_DENOMINATOR=1,
CHECK_INVALID=1`), and `exp_lut` at `REGISTERED=1` (block test). The instantiated
configuration is mandatory; the other supported configurations stay correct (their tests
are part of the frozen regression).

## Clock, reset, CDC

- One clock, `clk` (10 MHz target, `CLOCK_PERIOD` 100 ns).
- Reset: `rst_n && ena`, synchronous active-low, into the controller and divider. Many
  datapath flops are deliberately unreset: the mac ring, `S`, `L`, `q`, `token`, `pos`,
  `nibble`, `M`, divider datapath, top `sck_sync`, `cs_sync`, `config_chain`. Correctness
  must not depend on their power-up values. Formal proofs leave them unconstrained.
- Asynchronous inputs: host SCK `ui_in[0]` and CS# `ui_in[2]` pass through 2-flop
  synchronizers plus 1 edge flop (`sck_sync`, `cs_sync`). **These synchronizers are protected:
  no optimization may remove or merge them.** MOSI `ui_in[1]` is sampled unsynchronized by
  design (host holds it ±4 clk around the SCK rise; `docs/pin-protocol.md`).
- Flash IO (`uio_in[5:4], uio_in[2:1]`) is sampled in the `clk` domain against chip-generated
  SCK (`clk`/4); no CDC.

## Module interfaces and invariants (to distribute to agents)

1. **ripple_add #(N)**: combinational; `s = (a + b + cin) mod 2^N`. Instances N=22 (shared
   score/V adder), N=12 (weight sum L).
2. **max_reg**: `M <= S_in` when `en && (first || S_in > M)` (signed 22-bit); else hold. No reset.
3. **exp_lut #(REGISTERED)**: `W = round(255·e^(−D'/4))`, `D' = round_half_up(D / 2^shift)`,
   table of 25 non-zero entries, 0 beyond; `D` treated as unsigned 22-bit (`D >= 2^20` → 0).
   `REGISTERED=0`: combinational, `done = start`. Must match `exp_weight()` in
   `python/src/attention_model.py`.
4. **divider #(LATCH_DENOMINATOR, CHECK_INVALID)**: `result = round(16·sum_in/denominator)`,
   ties away from zero, signed 12-bit; accepted `start` when idle; `done` one cycle,
   exactly 24 cycles after accept (23 divide steps + round); `shift` shifts `result` left,
   a completing division overrides; `busy`. Instantiated contract: denominator stable from
   start to done, denominator > 0, in-range result.
5. **mac_unit #(OUTPUTS)**: shared 22-bit adder for score MAC (`S`) and V accumulation ring
   of OUTPUTS×20-bit sums rotating every clock; `L` weight sum; see header comment.
6. **attention_controller #(OUTPUTS)**: 8-state FSM, tape-driven quad-SPI 0x6B read, exact cycle
   counts: fresh run 162 + 2064·N clk to first division, continue run 1040·N
   (INTEGRATION_LOG §11/§12). These latencies are part of the contract.
7. **tt_um_attention_head_gf**: SPI target (mode 0), pin map in `info.yaml` /
   `docs/pin-protocol.md`, `uio_oe` pattern, DRDY timing rules.

## Existing verification inventory

| Suite | Runner | Scope | Baseline |
|---|---|---|---|
| python | `pytest python/test_attention_model.py` | golden model | 11 passed |
| divider | `test/divider/run.py` (Verilator) | 1,088,022 vectors vs `divide_round`, shift | pass |
| controller | `test/controller/run.py` (Verilator) | 79 cases × OUTPUTS 8/4/2, flash model | pass |
| top | `test/top/run.py` (cocotb/icarus) | pin-level SPI host + quad flash | 3 pass, 1 skip (SmolLM data absent) |
| tt_make | `test/Makefile` | TT template flow, same tests | 3 pass, 1 skip |
| blocks | `test/blocks` (cocotb) | mac_unit, max_reg, exp_lut (exhaustive) | pass |

There are no SymbiYosys or EQY artifacts. Driver: `pd_flow/scripts/regress.sh <logdir>`.
Logs: `pd_flow/baseline/regression/`.

## Tools validated

| Tool | Where | Status |
|---|---|---|
| Yosys 0.71 | native | ok |
| SBY, EQY | native, **run with `/usr/local/bin/python3`** (Homebrew `python3` lacks `click`) | smoke tests reproduced in isolation: counter k-induction PASS, example SAT equivalence PASS |
| Z3 4.x (5.4.1 reported), yosys-smtbmc, yosys-abc | native | ok |
| Verilator 5.046, Icarus | native | ok |
| cocotb 2.0, pytest 8.4 | `/usr/local/bin/python3` | ok |
| LibreLane 3.0.14 | Docker `ghcr.io/librelane/librelane:3.0.14` via `tt/tt_tool.py --harden` | baseline harden ok |
| OpenROAD, OpenSTA, Magic 8.3.623, Netgen 1.5.316, KLayout 0.30.7 | container | present |
| KLayout | host `/Applications/klayout.app` | present |
| **ngspice / Xyce** | **absent on host and container** | **blocker for SPICE characterization (Phase 4)** |

Environment notes:
- The project path contains a space (`2B ECE`); `tt_tool.py` does not quote paths. Hardening
  runs in the space-free mirror `/Users/samuelzhang/ttharden/attention_head_gf` (rsync of the
  project, excluding `build`, `pdk`, `pd_flow`, `codex-reference`). `tt/` was copied from
  `~/ttsetup/reference/tt` (commit `21568ef`); the reference is unmodified.
- Docker VM: 12 CPUs, 7.65 GiB memory (not 64 GB). Physical runs must stay within ~7 GB.
- Container PDK root: `~/ttsetup/pdk/ciel/gf180mcu/versions/54435919abffb937387ec956209f9cf5fd2dfbee`
  (`gf180mcuD`), mounted at the same path.

## Baseline metrics

### Mapped area (`pd_flow/scripts/synth_area.py`, Yosys 0.71, `synth -flatten`, default ABC, 7-track TT 025C 3V30)

| Module (as instantiated) | Area µm² | Cells | Flops |
|---|---:|---:|---:|
| ripple_add N=22 | 2,146.9056 | 95 | 0 |
| ripple_add N=12 | 1,148.0896 | 50 | 0 |
| max_reg | 3,360.8512 | 135 | 22 |
| exp_lut (REGISTERED=0) | 2,414.7200 | 102 | 0 |
| divider (0, 0) | 8,804.9472 | 344 | 56 |
| mac_unit (OUTPUTS=8) | 20,573.4144 | 610 | 194 |
| attention_controller (8) | 40,207.2832 | 1,397 | 314 |
| tt_um_attention_head_gf (8) | 42,145.6448 | 1,454 | 329 |

### Full-project LibreLane harden (Docker, `tt_tool.py --harden`, 82 s)

| Metric | Value |
|---|---|
| Die / core area | 55,712 / 51,967 µm² |
| Std-cell area (incl. tap/fill-free cells) | 46,819.2 µm² |
| Utilization | 90.09% |
| Instances (std cells / all) | 1,942 / 2,863 |
| Setup WNS (worst corner ss_125C_3v00) | +41.79 ns @ 100 ns |
| Hold WNS (worst, min_ff_n40C_3v60) | +0.109 ns |
| Setup / hold violations | 0 / 0 |
| Max slew violations | **381 (ss), 117 (tt)**: pre-existing, high-fanout nets behind `fanout*` buffers |
| Max cap / max fanout violations | **1 / 11**: pre-existing |
| Route DRC, antenna, Magic DRC, illegal overlap | 0, 0, 0, 0 |
| LVS | clean (0 errors) |
| KLayout DRC | not run (TT config `RUN_KLAYOUT_DRC: 0`) |
| Route wirelength | 53,890 µm |
| Power (tt) | 3.05 mW |

Evidence: `pd_flow/baseline/harden/` (metrics, logs, GDS/LEF/netlists, STA reports, hashes).

The baseline is **not electrically clean**: slew, cap and fanout violations exist before any
change. They come from the area-tuned repair settings in `src/config.json`. They are recorded,
not fixed, because the workflow preserves synthesis/physical configuration. No change may
increase them.

## Feasibility notes for Phases 3 and 4

- The die is fixed at one 1×1 tile, and the baseline already fits at 90% utilization. Area
  gains therefore show up as utilization headroom, not as a smaller allocated die.
- Hard-macro integration costs halos, PDN hookup and placement freedom. For this 90%-full tile
  it may increase total area or fail placement. Each module's integration is measured against
  the flat baseline. If a custom macro is larger or fails to place, the flat implementation
  stays in the shipped configuration, and the macro result is reported as evidence.
- For std-cell-based custom layouts (tetrising), timing and power characterization can come
  from OpenSTA with extracted parasitics. Transistor-level SPICE verification and
  characterization need ngspice, which is absent.
