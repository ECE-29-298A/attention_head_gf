---
name: rtl-reviewer
description: Specialized skill for static RTL review and audit of Verilog and SystemVerilog designs. Enforces assignment discipline (blocking vs non-blocking), complete branch coverage (latch prevention), deterministic reset protocols, and clock domain crossing (CDC) sanitization.
---

# RTL Reviewer Skill

This skill guides coding agents through static code audits of Verilog and SystemVerilog register-transfer level (RTL) designs. Use this skill whenever reviewing, refactoring, or evaluating newly written hardware modules.

---

## 1. Core Review Rubric (The 5 Golden Rules)

### Rule 1: Assignment Discipline (No Race Conditions)
- **Sequential Logic (`always @(posedge clk)`)**: MUST use non-blocking assignments (`<=`). Never use blocking (`=`) inside sequential blocks unless declaring immediate local variables.
- **Combinational Logic (`always @*` or `always_comb`)**: MUST use blocking assignments (`=`). Never use non-blocking (`<=`) inside pure combinational logic.
- **Why**: Mixing assignments causes simulation-synthesis mismatches where simulator event queues yield different results than actual synthesized hardware.

### Rule 2: Complete Branch Coverage (Prevent Accidental Latches)
- Combinational `always @*` blocks MUST assign default values to all outputs at the beginning of the block, or cover all permutations in `if-else` and `case` branches.
- Every `case` statement in combinational logic MUST include a `default:` branch.
- **Why**: Incomplete assignments infer transparent level-sensitive latches, consuming extra silicon and causing static timing analysis (STA) closure nightmares.

### Rule 3: Deterministic Reset Protocol (Presence + Polarity)
- Every sequential block MUST have a reset in its sensitivity list (`MISSING_RESET` fires otherwise); registers must never power up unknown.
- Clearly distinguish between **synchronous** (`always @(posedge clk)`) and **asynchronous active-low** (`always @(posedge clk or negedge rst_n)`).
- Clearly distinguish between **synchronous** (`always @(posedge clk)`) and **asynchronous active-low** (`always @(posedge clk or negedge rst_n)`).
- Never mix active-high and active-low reset conventions within the same module hierarchy without explicit adaptation.
- Every state element (flip-flop) MUST have a clean, unambiguous reset state.

### Rule 4: Explicit Bitwidth Alignment & Truncation
- Avoid implicit vector truncations or zero-extensions (e.g., assigning a 16-bit accumulator to an 8-bit register without explicit slicing `[7:0]`).
- Pay attention to arithmetic overflow: Adding two $N$-bit numbers requires $N+1$ bits to avoid silent overflow.

### Rule 6: Synthesis-Safe Constructs (No Simulation-Only Code)
- **No `initial` blocks** in synthesizable RTL: synthesis ignores them, so silicon behavior diverges from simulation. Move stimulus to `*_tb` testbenches.
- **No `#delay` operators** outside testbenches.
- **Every `case` needs `default:`** (see Rule 2) — the `CASE_DEFAULT_MISSING` and `LATCH_RISK` checks enforce this mechanically.

### Rule 7: Assertion Hygiene for Formal
- Solver-only SVA lives behind `` `ifdef FORMAL `` / `` `endif `` because iverilog cannot parse `assert`. Prove with `-DFORMAL`.
- Every property binds one explicit clock and reset with declared polarity (`no_x_after_reset`, `reset_value`, `req_ack_handshake`, `onehot` templates).
- A passing lint is not a proof: only a PROVEN formal verdict gates signoff.

### Rule 5: Clock Domain Crossing (CDC) Sanitization
- Never sample an asynchronous or cross-clock-domain signal directly into combinational logic.
- Single-bit control signals: Route through a standardized 2-Flip-Flop (2-FF) synchronizer.
- Multi-bit data buses: Use an asynchronous FIFO or Gray-code pointer synchronizer; never synchronize multi-bit binary counters with independent 2-FF synchronizers.

---

## 2. Examples: Anti-Pattern vs. Production-Grade RTL

### ❌ Anti-Pattern: Race Conditions & Inferred Latches
```verilog
// BAD: Inferred latch on 'valid', blocking assignment in sequential block
module bad_alu (
    input  wire       clk,
    input  wire [1:0] op,
    input  wire [7:0] a, b,
    output reg  [7:0] out,
    output reg        valid
);
    // Incomplete case in combinational block -> transparent latch on 'valid'!
    always @* begin
        case (op)
            2'b00: begin out = a + b; valid = 1'b1; end
            2'b01: begin out = a - b; end // missing valid = ? -> LATCH!
        endcase
    end

    // Sequential block using blocking '=' -> simulation race condition!
    always @(posedge clk) begin
        out = a & b; 
    end
endmodule
```

### ✅ Production-Grade RTL
```verilog
// GOOD: Safe combinational defaults, non-blocking sequential logic, explicit widths
module good_alu (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [1:0] op,
    input  wire [7:0] a, b,
    output reg  [7:0] out,
    output reg        valid
);
    reg [7:0] next_out;
    reg       next_valid;

    // Combinational next-state logic with safe defaults
    always @* begin
        next_out   = 8'h00;
        next_valid = 1'b0;

        case (op)
            2'b00: begin
                next_out   = a + b;
                next_valid = 1'b1;
            end
            2'b01: begin
                next_out   = a - b;
                next_valid = 1'b1;
            end
            2'b10: begin
                next_out   = a & b;
                next_valid = 1'b1;
            end
            default: begin
                next_out   = 8'h00;
                next_valid = 1'b0;
            end
        endcase
    end

    // Synchronous registered stage with active-low reset
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            out   <= 8'h00;
            valid <= 1'b0;
        end else begin
            out   <= next_out;
            valid <= next_valid;
        end
    end
endmodule
```

---

## 3. Agent Review Checklist
When an agent reviews RTL code, it must verify each item:
- [ ] Are all sequential assignments non-blocking (`<=`)?
- [ ] Are all combinational assignments blocking (`=`)?
- [ ] Are all `case` statements equipped with a `default` case?
- [ ] Are default output values assigned at the top of every `always @*`?
- [ ] Is there an unambiguous reset condition for all flip-flops (present in sensitivity, polarity matching the `if` branch)?
- [ ] Are `initial` blocks and `#delay`s absent from synthesizable RTL?
- [ ] Is solver-only SVA behind `` `ifdef FORMAL `` with explicit clock/reset?
- [ ] Score context: `mcp-rtl-review` computes 100 − 15·errors − 5·warnings over 12 rules (`..._REVIEW`, `MISSING_RESET`, `LATCH_RISK`, `MULTIPLE_DRIVERS`, `CASE_DEFAULT_MISSING`, `INITIAL_BLOCK_SYNTH`); gate at ≥ 70 with zero errors.
- [ ] Are cross-clock-domain signals isolated with synchronizers?
