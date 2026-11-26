# ripple_add: verification specification

Design under test: `pd_flow/baseline/original_rtl/ripple_add.v` (golden; any later
implementation is checked against this same contract with `run_all.sh --rtl FILE`).
Sources used to derive the requirements: the RTL header and body, and the two instances in
`pd_flow/baseline/original_rtl/mac_unit.v` (lines 41 and 43).

## 1. Function

`ripple_add #(parameter N = 16)` is a purely combinational N-bit adder with carry in. It
returns the low N bits of `a + b + cin`; the carry out of the most significant bit is dropped
(the result wraps exactly like Verilog `+` at width N). The internal structure (ripple
chain of full adders) is an implementation choice and is **not** part of the contract.

## 2. Use in the design

| Instance | N | a | b | cin | What it relies on |
|---|---:|---|---|---|---|
| `mac_unit.adder` | 22 | `S` (score) or sign-extended `O0` / 0 (V ring) | `term` or `~term` | `neg` | mod-2^22 add; when `neg = 1`, `a + ~term + 1 = a - term` (two's-complement subtract). Signed operands are interpreted by the caller; bit patterns are identical for signed and unsigned wrap-around addition. |
| `mac_unit.l_adder` | 12 | `L` or 0 | `{4'b0, W}`, W in 0..255 | 0 | mod-2^12 add of an 8-bit weight into the 12-bit weight sum. |

## 3. Requirements

| ID | Requirement |
|---|---|
| R1 | For every N used and every input `a, b` in [0, 2^N) and `cin` in {0, 1}: `s == (a + b + cin) mod 2^N`. |
| R2 | Overflow wraps: when `a + b + cin >= 2^N`, `s == a + b + cin - 2^N` and no carry out is produced or required (no extra port). |
| R3 | The module is purely combinational: no flops, latches or memories; no combinational loops, undriven or multiply-driven nets; `s` depends only on the current `a, b, cin`. |
| R4 | Subtract use (N = 22 instance): with `b = ~x` and `cin = 1`, `s == (a - x) mod 2^N` for all `a, x`. (Follows from R1, but is checked separately because `mac_unit` depends on it.) |
| R5 | Interface: exactly the ports `a` (input [N-1:0]), `b` (input [N-1:0]), `cin` (input, 1 bit), `s` (output [N-1:0]); parameter `N` with default 16. Port names, directions and widths must not change (the `mac_unit` instances connect by name). |
| R6 | The instantiated configurations N = 22 and N = 12 meet R1 to R5 (mandatory). |
| R7 | The module stays correct for other values of the parameter: R1, R3, R5 hold for N = 1 to 12, 16, 32 and 64 (the parameter is generic; N = 1 is the degenerate single full adder). |
| R8 | The RTL is lint-clean under `verilator --lint-only -Wall` and Yosys `check -assert` for the checked N, with one documented waiver: Verilator `UNUSEDSIGNAL` on `c[N]` (the internal carry out of the last full adder, computed and dropped by design, see R2). The waiver matches only that exact message and bit (`lint/check_lint.py`); any other warning fails, and an implementation with different internal names must be lint-clean or have its own waiver reviewed. Status `pass-with-waiver`. |

Out of scope: timing, area and power (Phase 2+ metrics, not functional requirements);
X-propagation (the module has no X sources; 4-state X inputs are not specified); N = 0 and
N > 64 (not used; N > 64 is left out only because the C++ testbench uses 64-bit words, the
formal proof is width-generic in principle).

## 4. Verification approach

| Method | What | Strength |
|---|---|---|
| Golden model | `model/golden_model.py`: `s = (a + b + cin) % 2**N` on unbounded Python integers, plus hand-computed known-answer tests (`selftest`). Independent of the RTL's bit-level structure. | reference |
| Exhaustive simulation | Verilator, every (a, b, cin) for N = 1..12 (N = 12: 2^25 = 33,554,432 vectors). Each output is checked against an in-testbench uint64 reference, and a checksum `sum(s * splitmix64(idx)) mod 2^64` over all outputs (idx encodes a, b, cin) is compared with the same checksum computed independently from the Python model (numpy), so the in-testbench reference is itself cross-checked. | complete for those N |
| Golden vectors | Python model writes directed corners (all-zero, all-ones, walking 1/0, alternating, MSB, full propagate, generate-at-bit-k, subtract operands `~x` with cin = 1, mac_unit-style `term`/`~term` for N = 22, the `{4'b0, W}` range for N = 12) plus 200,000 seeded random vectors (uniform, long-carry-chain and sparse/dense mixes). Applied on Verilator for N = 12, 16, 22, 32, 64 and also on Icarus (second simulator) for the instantiated N = 12 and 22; every simulator must check every vector (count must equal the generator's count). Icarus is not used for N = 16, 32, 64 because its event-driven evaluation of the long ripple chain makes 200k vectors take minutes there. | sampled |
| Random simulation | Verilator, xorshift64* random with half of the vectors forced into long carry chains: 50 M vectors for N = 22, 10 M for N = 16, 32, 64. | sampled |
| Formal proof | SymbiYosys `mode prove`, smtbmc/Z3, harness `formal/ripple_add_props.sv`: `a_sum: s == ({1'b0,a} + {1'b0,b} + cin)[N-1:0]` (R1, R2) and `a_sub: ripple_add(a, ~x, 1) == a - x` (R4), all inputs free, no assumptions. N = 1, 2, 3, 4, 5, 7, 8, 12, 16, 22, 32, 64; independently with `abc pdr` for N = 12 and 22. | proven (unbounded) |
| Covers | SBY `mode cover`, 11 covers (overflow wrap, largest unwrapped sum, carry propagating through all N bits with cin = 1, all-propagate without carry, cin = 1 with a = all-ones, all-ones + all-ones + 1, all zero, cin only, MSB generate with wrap, subtract with borrow, a - a). N = 1, 4, 8, 12, 22, 32. Every cover must be reached. | reachability |
| Negative control | Same harness with a deliberately wrong reference (`s == a + b`, cin ignored) must be refuted with a counterexample (N = 12, 22). Shows the flow detects a mismatch; it is not a mutation of the DUT. | checker sanity |
| Structure / interface | Yosys `hierarchy -check; proc; flatten; check -assert`, assertion of zero state cells, `write_json` port check (`lint/check_interface.py`); Verilator `-Wall` lint. N = default (16), 1, 8, 12, 16, 22, 32, 64. | static |

### Why the depth-1 proof is unbounded (complete)

The proof harness contains no state elements: the SBY script asserts that the elaborated
model has no `$ff`, `$dff*`, `$adff*`, `$sdff*`, `$aldff*`, latch, `$sr`, memory or
`$anyinit` cells, and R3 is also checked separately on the DUT. The transition relation is
therefore empty, and at each time step the assertions are a function of that step's free
inputs only. The base case at step 0 asks the SMT solver whether any assignment of
`a, b, x, cin` (all 2^(3N+1) values, symbolically) violates an assertion; UNSAT means none
does. The induction step is trivially valid because there is no state to carry a
violation forward. SBY reports "successful proof by k-induction", and `abc pdr` (a separate
engine) agrees. So `proven` here covers all inputs at all times for that N. The proof is per
parameter value: it is complete for each listed N, not for all N at once.

There are no assumptions, so the assertions cannot be vacuous through over-constraint; the
covers additionally show that the interesting regions (wrap, full carry chain, subtract
borrow) are reachable in the same model, and `run_all.sh` checks that the model really
contains 2 asserts (and 11 covers in cover runs).

## 5. Result labels (results.json)

`proven` (unbounded formal proof), `pass-exhaustive` (all inputs simulated for that N),
`pass-sampled` (directed/random simulation; not a proof), `covered` (all covers reached),
`failed-as-expected` (negative control refuted, which is the required outcome), `pass`
(structure, model self-test, build), `pass-with-waiver` (lint with only the R8 waiver), `failed`, `timed-out`, `inconclusive` (tool or infrastructure error, e.g. an SBY traceback or no PASS/FAIL status; no verdict, counts as not ok). Each SBY task runs from its own directory and copy of `ripple_add.sby`, so parallel tasks never share SBY's status database. Each item also carries
`ok: true/false`; `all_ok` is the conjunction.
