# ripple_add: expected behaviour (independent derivation, Agent 2)

Derived only from the golden RTL `pd_flow/baseline/original_rtl/ripple_add.v` and its two
instantiations in `pd_flow/baseline/original_rtl/mac_unit.v` (lines 41 and 43), before
reading any of Agent 1's verification artifacts.

## Interface

```
module ripple_add #(parameter N = 16) (
    input  wire [N-1:0] a, b,
    input  wire         cin,
    output wire [N-1:0] s );
```

No clock, no reset, no state, no carry-out port. Default `N = 16`.

## Function

E1. `s == (a + b + cin) mod 2^N` for **every** `a, b in [0, 2^N)`, `cin in {0,1}`.
    The carry out of bit N-1 (`c[N]`) is dropped (wraps like `+`).
E2. Purely combinational: `s` depends only on the current `a, b, cin`. No latches, no
    flops, no memory, no combinational loop. Output fully defined (no X/Z) for defined inputs.
E3. Bitwise view (the golden structure, not a requirement on an implementation):
    `s[i] = a[i] ^ b[i] ^ c[i]`, `c[0] = cin`,
    `c[i+1] = a[i]&b[i] | c[i]&(a[i]^b[i])`. A replacement implementation (any adder
    architecture) only has to meet E1/E2; E3 is not a contract obligation.

## How mac_unit uses it

### `adder`: `ripple_add #(.N(22))`
`.a(a), .b(neg ? ~term : term), .cin(neg), .s(sum)`

- `cin = neg` is the two's-complement subtract trick: when `neg = 1`, `b = ~term` and
  `cin = 1`, so `sum = a - term (mod 2^22)`. Both `cin = 0` and `cin = 1` are used.
- Score mode (`accum_mode = 0`): `a = S` (signed 22-bit), all 22 sum bits are stored back
  into `S`. `neg = top ^ subtract` can be 1 with `bit_on = 0`, giving `b = 22'h3FFFFF`,
  `cin = 1`: a full-length carry chain (`sum = a`). Full-width propagate chains and the
  wrap from bit 21 are therefore functionally live.
- Accumulate mode: `a` is 0 (load) or the sign-extended 20-bit head `O0`; only `sum[19:0]`
  are used (`sum[21:20]` explicitly unused). The contract must still cover all 22 bits,
  because score mode uses them.
- Operands can be any 22-bit pattern reachable from `S`/`M` (unreset flops, `M` from
  max_reg), so the contract must not restrict `a` or `b`.

### `l_adder`: `ripple_add #(.N(12))`
`.a(first ? 12'd0 : L), .b({4'b0, W}), .cin(1'b0), .s(L_next)`

- `cin` tied to 0; `b[11:8]` tied to 0 in this context.
- The module itself must still be correct for every `b` and `cin` (the contract is on the
  module, not on the context). A context-only (cin=0, b<256) check would be a weaker,
  separately labelled result and is not sufficient as the module contract.

## What a complete contract must cover

C1. Full functional equivalence to an **independent** reference (`a + b + cin` with
    truncation, not a copy of the RTL's gate equations) at **N = 22** and **N = 12**,
    all inputs, both `cin` values. Formal (SAT/SMT over all inputs) or exhaustive
    simulation. N=12 is exhaustively simulable (2^25 vectors); N=22 (2^45) is not, so N=22
    needs a formal proof, with random + directed simulation as supporting evidence only.
C2. No assumptions restricting `a`, `b`, `cin` (no overconstraint). Any `assume` must be
    justified and shown not to restrict inputs.
C3. Non-vacuity: covers showing both `cin` values, a wrap (carry out of MSB), a full-length
    propagate chain (e.g. `a = all ones, b = 0, cin = 1` or `b = ~a, cin = 1`), and `s`
    reaching 0 and all-ones, at each N.
C4. Directed corner cases at both N: zeros, all ones, `a = ~b` with cin 0/1, MSB-only
    operands, alternating patterns, single-bit carries at bit 0 and at bit N-1.
C5. Statelessness/combinational: lint (Verilator `-Wall`), no latches/flops after synthesis,
    no combinational loops. A depth-1 BMC of a combinational property over unconstrained
    inputs is a complete proof only if the design has no state (so there is nothing for
    deeper steps to add). That must be justified by evidence (synthesised netlist has 0
    cells of `$dff`/`$dlatch` type, or equivalent).
C6. Parametric sanity: default N=16 (and ideally N=1 and a third width) still elaborates
    and is correct, since the module is parameterised; secondary to C1.
C7. The checks must be implementation-agnostic so they can be rerun on a replacement RTL
    (`--rtl <dir>`), and must fail on a faulty RTL (mutation testing).
C8. Honest labelling per AGENT_CONTEXT: proven (unbounded) only where justified; random
    simulation is "pass (sampled)", not a proof.
