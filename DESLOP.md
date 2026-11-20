# DESLOP — Verilog plumbing audit

Audit only; no code was changed. Scope: everything in `src/`, plus the Verilog testbenches where they pin dead behaviour in place.

- **A** = most important (real area, or the tests cover something other than what ships)
- **B** = worth doing (small area, or one fewer layer to reason about)
- **C** = nice to have (cosmetic)

Nothing here was synthesized. "Saves" figures are flop/gate counts read off the RTL, not measured area. Every removal needs a re-run of `test/` and the GF180 one-tile flow.

---

## A — most important

> **Status: A1–A6 are done.** Mapped area went from 54,607.80 to 51,890.14 µm² (Yosys 0.69, GF180 7-track TT). The links below point at code that no longer exists.

### A1. The SPI stack is built for quad/octal, but the chip only does 1-bit SPI
[qspi_read_adapter.v:40](src/Memaccess/qspi_read_adapter.v#L40) ties `wide` to `1'b0`. Only the `0x03` 1-1-1 read is ever issued. Everything below exists for a mode that is never used:

- `LANES` parameter, `WIDE_LAST`, the `wide` port and `wide_r` flop ([spi_multi_io_byte.v:24-30](src/Memaccess/spi_multi_io_byte.v#L24-L30)).
- The wide branches of the `io_o`, `io_oe` and `shift` muxes ([spi_multi_io_byte.v:34-37](src/Memaccess/spi_multi_io_byte.v#L34-L37), [:51-53](src/Memaccess/spi_multi_io_byte.v#L51-L53)).
- A 4-bit `sampled` register where only `sampled[1]` is read.
- [qspi_byte.v](src/Memaccess/qspi_byte.v): a 25-line wrapper that only sets `LANES=4`.
- [ospi_byte.v](src/Memaccess/ospi_byte.v): the 8-lane wrapper. It is not in `info.yaml` or `test/Makefile`; only `test/spi_byte/` builds it.
- `tx_en` / `last` ports and their `tx_en_r` / `last_r` flops: both are a pure function of `byte_index` in the adapter.

The adapter and the byte engine are two FSMs joined by a start/ready/done handshake, for a transaction that is always the same 40 bits (8 command, 24 address, 8 data). One shifter with a 6-bit counter does the same job in roughly 40 lines instead of three files and 190 lines.

Synthesis already prunes most of the constant-`wide` logic, so the gain is mostly source and test size. The real gate savings are the second FSM, the handshake and the `tx_en_r` / `last_r` / `sampled[3:2,0]` flops.

Knock-on: `test/spi_byte/` (four files) tests wide and octal modes that do not ship.

### A2. Checks for inputs the design cannot produce
Each of these guards a case the file's own comment calls impossible in-system.

- **Divider `invalid` and `overflow`** ([divider.v:37](src/divider.v#L37), [:47](src/divider.v#L47), [:58](src/divider.v#L58), [:73](src/divider.v#L73)). Zero denominator, `sum == -524288`, and a result outside 12 bits all force `result = 0`. None can happen: the max-score token always has W = 255, so L ≥ 255; |O| ≤ 522240; and a weighted mean of INT8 values times 16 fits in 12 bits. Cost: a 12-bit zero detect, a 20-bit constant compare, one flop, an 11-bit OR, a 13-bit compare and a 12-bit zeroing mux.
- **`exp_lut` clamp for M < S** ([exp_lut.v:53](src/exp_lut.v#L53), [:60-61](src/exp_lut.v#L60-L61)). M is the true maximum of the same scores recomputed in pass 2, so `diff[22]` is never set. Cost: the 23rd subtractor bit and an 8-bit mux.
- **Token-count range check, done twice.** [project.v:25](src/project.v#L25) refuses the config handshake unless N is 1..16. [attention_controller.sv:97](src/attention_controller.sv#L97) checks the same range again in `start_ready`. In the chip the second check can never fail. Keep the top-level one.

Removing these means deleting the matching test cases: "invalid inputs" in `tb_divider.sv`, and "Accepted N=0 / N=17" at [tb_controller.sv:231-236](test/controller/tb_controller.sv#L231-L236).

### A3. `LATCH_CONFIG` and `LATCH_DENOMINATOR`: block tests cover the variant that does not ship
- The chip sets `LATCH_CONFIG = 0` ([project.v:39](src/project.v#L39)) and `LATCH_DENOMINATOR = 0` ([attention_controller.sv:136](src/attention_controller.sv#L136)).
- `tb_controller.sv` and `tb_divider.sv` both instantiate with the defaults (= 1). They then wiggle the inputs mid-run to prove latching ([tb_controller.sv:291](test/controller/tb_controller.sv#L291), [tb_divider.sv:30](test/divider/tb_divider.sv#L30)).

So the 100k-vector divider test and the full controller test verify generate branches that are dead in silicon. The shipped branches are covered only by the handful of queries in `test/top`.

Delete both parameters and the latching branches ([attention_controller.sv:82-89](src/attention_controller.sv#L82-L89), [divider.v:27-35](src/divider.v#L27-L35)), and drop the mid-run input wiggling from the two testbenches. This is the highest-risk item to leave as is.

### A4. The adapter re-registers an address the controller already holds stable
[qspi_read_adapter.v:23](src/Memaccess/qspi_read_adapter.v#L23) and [:35](src/Memaccess/qspi_read_adapter.v#L35) latch a 24-bit `address`. `mem_addr` is decoded from `return_state`, `token`, `group`, `chunk_sel` and `bit_index`. None of those change until `mem_rsp_valid`, which comes after the address bytes have been shifted out. The register is a copy of a stable value.

- Saves up to 16 flops. The top 8 bits are constant zero and are probably pruned already (not verified).
- `FLASH_BASE` ([qspi_read_adapter.v:5](src/Memaccess/qspi_read_adapter.v#L5)) is always 0, so the 24-bit add is a no-op. Drop the parameter.

### A5. Dead files in `src/`
None of these is in `info.yaml` or `test/Makefile`. `docs/integration-report.md` already lists them as unused.

- [src/Memaccess/addr_gen.v](src/Memaccess/addr_gen.v): 0 bytes.
- [src/custom_mult.sv](src/custom_mult.sv): an empty `multiplier` module with an unused `OUT_WIDTH`.
- [src/gate_adder.v](src/gate_adder.v): `full_adder`, never instantiated. `ripple_add` inlines the same equations.
- [src/Memaccess/ospi_byte.v](src/Memaccess/ospi_byte.v): see A1.

### A6. A write channel and status ports that go nowhere
- `mem_write` and `mem_wdata` are constant 0, "kept for adapter compatibility" ([attention_controller.sv:33-35](src/attention_controller.sv#L33-L35), [:100-101](src/attention_controller.sv#L100-L101)). The adapter has no write port. They are wired through `project.v` only to end in `_unused` ([project.v:66-67](src/project.v#L66-L67)), and `tb_controller.sv:79` asserts they stay 0.
- `busy` on the controller and `busy` on the divider are unused in the chip. Both end in `_unused` sinks.

Zero gates, but four ports, six wires and two `_unused` lines of noise.

---

## B — worth doing

> **Status: B1–B7 and B9 are done** (B8 no longer applies: `spi_read` has no async reset). Beyond the list: scores now run one component at a time, so the 32-bit Q register is gone; flash bits shift straight into the operand register, so the SPI byte register is gone; the divider keeps its result in the quotient register; `max_reg` and `score_mac` load on their first input instead of clearing (C7). Mapped area 51,890 → 45,221 µm², 329 → 260 flops. The flash map is now Q 0x000, K 0x400, V 0x800 (B7), and `uo_out` is undefined outside output-valid (B9).

### B1. Reset is ANDed into combinational outputs at three levels
- `project.v`: `active &&` on `cfg_ready` and `core_start` ([project.v:26](src/project.v#L26), [:35](src/project.v#L35)).
- Controller: `rst_n &&` on `start_ready`, `mem_req_valid`, `exp_start`, `div_start`, `out_valid` ([attention_controller.sv:97-117](src/attention_controller.sv#L97-L117)).
- Adapter: `rst_n &&` on `byte_start` and `req_ready` ([qspi_read_adapter.v:26](src/Memaccess/qspi_read_adapter.v#L26), [:37](src/Memaccess/qspi_read_adapter.v#L37)).

Every consumer already ignores its input while in reset: `exp_lut`, `divider` and the adapter FSM all take their reset branch first. After one clock in reset every state is IDLE and these signals are 0 anyway. The gating only matters for the first cycle of reset.

- `core_start` is gated three times: `active`, `core_start_ready` (which already contains `rst_n`), and again inside the controller as `start && start_ready`. It can be `stage == LAUNCH`.
- The two pin-facing ones (`cfg_ready`, `out_valid` on `uio[7]`) are the only ones with an argument for staying. The top test masks them during reset itself ([test_top_qspi.py:75-76](test/top/test_top_qspi.py#L75-L76)), so nothing checks them.

### B2. Resets on registers that are always written before they are read
- Controller: `return_state`, `last`, `token`, `group`, `second_pass`, `output_index`, `high_byte` ([attention_controller.sv:163-171](src/attention_controller.sv#L163-L171)). All are assigned at start or before first use. About 21 flops.
- `divider.result` (12 flops): only meaningful after `done`.
- `exp_lut.W` (8 flops): only meaningful after `done`.
- `max_reg` and `score_mac`: the `!rst_n` branch duplicates `clear`, which fires at `INIT` of every run ([max_reg.v:22-25](src/max_reg.v#L22-L25), [score_mac.v:32-35](src/score_mac.v#L32-L35)). The `rst_n` port can go from both. Roughly one gate each, mostly a clarity win.

Keep the resets on `state`, `done`, `bit_index` and `component`. `bit_index` is not re-initialised at start. `component` would be X forever in simulation.

Tests that pin this: `result == 0` after reset in `tb_divider.sv:15` and `:56`.

### B3. Ready signals that are always 1 when they are sampled
- `mem_req_ready`: one request is outstanding at a time, and the adapter is back in IDLE before the controller re-enters `MEM_REQUEST`. The wait at [attention_controller.sv:235](src/attention_controller.sv#L235) never stalls in the chip.
- `byte_ready`: the byte engine is back in IDLE before the adapter reaches `ISSUE` ([qspi_read_adapter.v:58](src/Memaccess/qspi_read_adapter.v#L58)), and before `req_ready` is sampled.
- `core_start_ready` in `LAUNCH` ([project.v:83](src/project.v#L83)): the controller is always idle by then.

`tb_controller.sv` randomises `mem_req_ready` stalls, which the real adapter never produces. Mostly absorbed if A1 is done.

### B4. `exp_lut` has a handshake around a fixed one-cycle delay
`done <= start` ([exp_lut.v:101](src/exp_lut.v#L101)), so `EXP_WAIT` always waits exactly one cycle. Drop the `done` flop and the `EXP_WAIT` state and go `EXP_START → VALUE_READ`.

Going further: M and S are both held for the whole accumulate step, so W could be purely combinational and the 8-bit W register could go too. That puts subtract, round, LUT, shift and the 20-bit ripple adder in one path. Check STA at the 100 ns clock before trying it.

### B5. `last`, `done` and `COMPLETE` duplicate state the wrapper already holds
- `last` ([attention_controller.sv:69](src/attention_controller.sv#L69), [:177](src/attention_controller.sv#L177)): `project.v` holds `count` stable through RUN, the same contract that `LATCH_CONFIG=0` relies on. `last` can be a wire `token_count - 1`. Saves 4 flops.
- `done` and the `COMPLETE` state: the wrapper only needs "run finished". `RUN: if (!core_busy)` does that. Saves 1 flop and 1 state, and gives `busy` a use (see A6).

### B6. Pass-through FSM states and a no-op assignment
- `QUERY_READY` ([attention_controller.sv:188](src/attention_controller.sv#L188)) does nothing. It exists so that `return_state` can double as the address-region select.
- `KEY_READY` ([:190](src/attention_controller.sv#L190)) sets `bit_index <= 0`, but `bit_index` is already 0 there: 4 Q reads plus 4 K reads wrap the 3-bit counter. No-op.
- `INIT` ([:185](src/attention_controller.sv#L185)) exists only to pulse `clear`. `score_mac` is cleared again at `SCORE_CLEAR` with `group == 0`, so its `INIT` clear is redundant. `max_reg` could clear on `state == IDLE`.
- `return_state` is a 5-bit register that takes 6 values. A 2-bit region select (Q/K/V) carries the same information.

22 states today. Removing these gets under 16, so `state` drops to 4 bits.

### B7. Unaligned memory bases cost adders; relocatable bases are tested but never used
- `K_BASE = 0x0040` and `V_BASE = 0x0440` ([attention_controller.sv:11-13](src/attention_controller.sv#L11-L13)) make `mem_addr` two real 10-bit additions ([:111-113](src/attention_controller.sv#L111-L113)). With aligned bases (Q `0x000`, K `0x400`, V `0x800`) the address is pure concatenation. This changes the flash layout, so the Python model and tests move with it.
- The `Q_BASE` / `K_BASE` / `V_BASE` parameters are never overridden in the chip. `test/controller/run.py:111` does a whole second build with relocated bases to test a configuration that does not ship.

### B8. One module uses async reset; the rest are synchronous
[spi_multi_io_byte.v:58](src/Memaccess/spi_multi_io_byte.v#L58) uses `negedge rst_n`. Its reset is `active = rst_n && ena`, a combinational signal ([project.v:24](src/project.v#L24)). The controller header says "All resets are synchronous". Make it synchronous like everything else. The top test already allows two clocks for CS to release.

### B9. `uo_out` is zeroed when not valid
[project.v:65](src/project.v#L65): 8 AND gates so the bus reads 0 outside `out_valid`. The host must qualify with `uio[7]` anyway. Waveform cosmetics only.

---

## C — nice to have

- **C1. Alias wires** in the controller: `weight = exp_weight`, `exp_max = maximum`, `exp_score = score`, `div_sum = o0` ([attention_controller.sv:91](src/attention_controller.sv#L91), [:103-105](src/attention_controller.sv#L103-L105), [:116](src/attention_controller.sv#L116)). Two names per signal. `tb_controller.sv` probes the aliases.
- **C2. `accum` exports O1, O2, O3** only for the controller to sink them in `_unused` ([attention_controller.sv:141](src/attention_controller.sv#L141)). Only `tb_controller.sv:153-156` reads them, and it could read `dut.accum_unit.O1` directly.
- **C3. Unreachable `default` arm** in `project.v` ([:85](src/project.v#L85)): all four 2-bit codes are named states. The `default` arms in `divider.v` and `qspi_read_adapter.v` cover a real spare code. Keep those.
- **C4. Comment slop** in `score_mac.v`: a pasted Python `dot()` at [:47-55](src/score_mac.v#L47-L55), plus "Clear the signal" and "S keeps its value, do nothing".
- **C5. Names say QSPI, behaviour is 1-bit SPI**: `qspi_read_adapter`, `qspi_byte`, "QSPI flash" in headers. Rename if A1 is done.
- **C6. `ripple_add` is hand-written, the divider uses plain `+` / `-`.** Pick one style. Whether the hand-rolled ripple saves area after ABC is unmeasured; run `scripts/gf180_one_tile.py` both ways before deciding.
- **C7. `max_reg` clear constant**: the 22-bit load of `-1040384` could use the same "first token loads" trick as `accum` (`en && (first || S_in > M)`). That removes `clear` and the constant.
- **C8. [benchmarks/spi_byte_baseline.v](benchmarks/spi_byte_baseline.v)**: an old copy of the byte engine kept for `scripts/spi_byte_gf180_area.py`. Delete both once the area comparison is no longer needed.
- **C9. `codex-reference/norm_odd.v`** and `codex-reference/attention-extended/norm_odd.v` are byte-identical.
- **C10. Stale docs**: `docs/blocks.md:64` and `docs/controller.md:51` still describe "four multipliers in parallel" in `accum`. The RTL is one shared shift-add adder.

---

## Suggested order

1. A5 and A6: pure deletions, no behaviour change.
2. A3: makes the block tests cover what ships. Do this before touching anything else.
3. A2, then A4.
4. A1: the largest rewrite. It absorbs B3 and B8.
5. B items, one at a time, each with an area measurement.

## Not plumbing, but noticed

Each byte read is its own CS transaction with a full `0x03` + 24-bit address: 40 SPI bits per data byte. Q/K/V are always read as four sequential bytes, so holding CS across a group would cut SPI clocks per group from 160 to 64. This is a performance change, not a cleanup.
