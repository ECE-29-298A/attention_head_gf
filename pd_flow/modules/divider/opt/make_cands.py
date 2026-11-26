#!/usr/bin/env python3
"""make_cands.py: writes candidates/ from the golden by exact text substitutions (each asserted once).
Header, ports, parameters, LATCH_DENOMINATOR generate block and handshake text stay byte-identical
unless a candidate's purpose is to change them."""
import os
G = open(os.path.join(os.path.dirname(__file__), "..", "snapshot", "divider.v")).read()
def sub(s, a, b):
    assert s.count(a) == 1, (a, s.count(a)); return s.replace(a, b)

# ---- c01: 19-bit dividend/quotient shift register (the 4 constant-zero dividend LSBs are not stored).
def c01(s):
    s = sub(s, "    reg [22:0] quotient; // Starts as abs(O) * 16 (< 2^23 when valid); shifted into a quotient in place.\n",
               "    reg [18:0] dq; // Starts as abs(O); dividend bits leave at the top, quotient bits enter at the bottom.\n")
    s = sub(s, "    wire [12:0] trial = {remainder_value, (state != ROUND) && quotient[22]};\n",
               "    // Steps 19..22 take the four zero LSBs of 16*abs(O); ROUND (step 23) takes 0 as well.\n"
               "    wire dividend_done = step[4] & (step[2] | (step[1] & step[0]));\n"
               "    wire [12:0] trial = {remainder_value, !dividend_done && dq[18]};\n")
    s = sub(s, "    wire [22:0] next_quotient = {quotient[21:0], subtract};\n", "    wire [18:0] next_dq = {dq[17:0], subtract};\n")
    s = s.replace("quotient[11:0]", "dq[11:0]")
    s = sub(s, "|quotient[22:12]", "high_quotient")
    s = sub(s, "    wire [12:0] rounded =",
               "    // Overflow (CHECK_INVALID only): the 11 high quotient bits (steps 0..10) no longer stay in dq.\n"
               "    wire high_quotient;\n"
               "    if (CHECK_INVALID) begin : g_high_quotient\n"
               "        reg seen;\n"
               "        always @(posedge clk) seen <= state == IDLE ? 1'b0 : seen | (subtract && step < 5'd11);\n"
               "        assign high_quotient = seen;\n"
               "    end else begin : g_no_high_quotient\n"
               "        assign high_quotient = 1'b0;\n"
               "    end\n"
               "    wire [12:0] rounded =")
    s = sub(s, "        quotient <= state == IDLE ? {magnitude, 4'b0} : next_quotient;\n",
               "        dq <= state == IDLE ? magnitude : next_dq;\n")
    return s
open("candidates/c01_dq19.v", "w").write(c01(G))

# ---- c02: c01 + quotient bits stored pre-complemented (q ^ negative), so the result needs no 12 XORs.
def c02(s):
    s = c01(s)
    s = sub(s, "    wire [18:0] next_dq = {dq[17:0], subtract};\n",
               "    // Quotient bits enter pre-complemented when negative (never read back as dividend bits).\n"
               "    wire [18:0] next_dq = {dq[17:0], subtract ^ negative};\n")
    s = sub(s, "    wire [12:0] rounded = {1'b0, dq[11:0]} + {12'b0, subtract};\n",
               "    wire [12:0] rounded = {1'b0, dq[11:0] ^ {12{negative}}} + {12'b0, subtract};\n")
    s = sub(s, "    wire [11:0] signed_result = (dq[11:0] ^ {12{negative}}) + {11'b0, subtract ^ negative};\n",
               "    wire [11:0] signed_result = dq[11:0] + {11'b0, subtract ^ negative};\n")
    return s
open("candidates/c02_dq19_flip.v", "w").write(c02(G))

# ---- c03: c02 + one 5-bit phase counter replaces state (2 bits), step (5) and the done flop.
# phase: 0 IDLE, 1..23 DIVIDE (step = phase - 1), 24 ROUND, 25 DONE (idle, done = 1).
def c03(s):
    s = c02(s)
    s = sub(s, "    output reg               done,\n", "    output wire              done,\n")
    s = sub(s, "    localparam [1:0] IDLE = 2'd0, DIVIDE = 2'd1, ROUND = 2'd2;\n    reg [1:0] state;\n",
               "    // phase: 0 idle, 1..23 divide steps 0..22, 24 round, 25 idle with done.\n"
               "    reg [4:0] phase;\n"
               "    wire idle = phase == 5'd0 || phase == 5'd25;\n"
               "    wire round_step = phase == 5'd24;\n")
    s = sub(s, "            if (state == IDLE) saved_divisor <= denominator;", "            if (idle) saved_divisor <= denominator;")
    s = sub(s, "    reg [4:0] step;\n", "")
    s = sub(s, "    wire dividend_done = step[4] & (step[2] | (step[1] & step[0]));\n",
               "    wire dividend_done = phase[4] & (phase[3] | phase[2]); // phase >= 20\n")
    s = sub(s, "seen | (subtract && step < 5'd11)", "seen | (subtract && phase < 5'd12)")
    s = s.replace("state == IDLE", "idle")
    s = sub(s, "    assign busy = state != IDLE;\n", "    assign busy = !idle;\n    assign done = phase == 5'd25;\n")
    s = sub(s, "        step <= idle ? 5'd0 : step + 5'd1;\n", "")
    i = s.index("    always @(posedge clk) begin\n        if (!rst_n) begin"); j = s.index("endmodule")
    s = s[:i] + """    always @(posedge clk) begin
        if (!rst_n) begin
            phase <= 5'd0;
            result <= 12'sd0;
        end else begin
            phase <= idle ? {4'd0, start} : phase + 5'd1;
            if (round_step) begin
                if (invalid || overflow) result <= 12'sd0;
                else result <= signed_result;
            end else if (shift) result <= {result[10:0], 1'b0};
        end
    end
""" + s[j:]
    return s
open("candidates/c03_dq19_flip_phase.v", "w").write(c03(G))

# ---- c04: c02 + 5-bit phase counter replacing state and step; the done flop is kept.
# phase: 0 IDLE, 1..23 DIVIDE (step = phase - 1), 24 ROUND.
def c04(s):
    s = c03(s)
    s = sub(s, "    output wire              done,\n", "    output reg               done,\n")
    s = sub(s, "    // phase: 0 idle, 1..23 divide steps 0..22, 24 round, 25 idle with done.\n",
               "    // phase: 0 idle, 1..23 divide steps 0..22, 24 round.\n")
    s = sub(s, "    wire idle = phase == 5'd0 || phase == 5'd25;\n", "    wire idle = phase == 5'd0;\n")
    s = sub(s, "    assign done = phase == 5'd25;\n", "")
    s = sub(s, "            phase <= 5'd0;\n            result <= 12'sd0;\n",
               "            phase <= 5'd0;\n            done <= 1'b0;\n            result <= 12'sd0;\n")
    s = sub(s, "            phase <= idle ? {4'd0, start} : phase + 5'd1;\n",
               "            phase <= idle ? {4'd0, start} : round_step ? 5'd0 : phase + 5'd1;\n            done <= round_step;\n")
    return s
open("candidates/c04_dq19_flip_phase_done.v", "w").write(c04(G))

# ---- c05: golden 23-bit register + pre-complemented quotient bits only (isolates the flip).
def c05(s):
    s = sub(s, "    wire [22:0] next_quotient = {quotient[21:0], subtract};\n",
               "    // Quotient bits enter pre-complemented when negative (never read back as dividend bits).\n"
               "    wire [22:0] next_quotient = {quotient[21:0], subtract ^ negative};\n")
    s = sub(s, "    wire [12:0] rounded = {1'b0, quotient[11:0]} + {12'b0, subtract};\n",
               "    wire [12:0] rounded = {1'b0, quotient[11:0] ^ {12{negative}}} + {12'b0, subtract};\n")
    s = sub(s, "|quotient[22:12]", "|(quotient[22:12] ^ {11{negative}})")
    s = sub(s, "    wire [11:0] signed_result = (quotient[11:0] ^ {12{negative}}) + {11'b0, subtract ^ negative};\n",
               "    wire [11:0] signed_result = quotient[11:0] + {11'b0, subtract ^ negative};\n")
    return s
open("candidates/c05_flip.v", "w").write(c05(G))

# ---- c06: c02 + state merged into the step counter (golden step values while busy, so the existing
# controller testbench probe dut.divider_unit.step keeps its meaning). step: 0..22 divide, 23 round,
# 24 idle (reset value; 25..31 unreachable, also decoded as idle). done flop kept.
def c06(s):
    s = c02(s)
    s = sub(s, "    localparam [1:0] IDLE = 2'd0, DIVIDE = 2'd1, ROUND = 2'd2;\n    reg [1:0] state;\n",
               "    // step: 0..22 divide steps, 23 round, 24 idle (reset value; 25..31 unreachable, decoded as idle).\n"
               "    reg [4:0] step;\n    wire idle = step[4] & step[3];\n    wire round_step = step == 5'd23;\n")
    s = sub(s, "    reg [4:0] step;\n    reg negative, invalid_r;\n", "    reg negative, invalid_r;\n")
    s = s.replace("state == IDLE", "idle")
    s = sub(s, "    assign busy = idle != IDLE;\n" if "idle != IDLE" in s else "    assign busy = state != IDLE;\n", "    assign busy = !idle;\n")
    s = sub(s, "        step <= idle ? 5'd0 : step + 5'd1;\n", "")
    i = s.index("    always @(posedge clk) begin\n        if (!rst_n) begin"); j = s.index("endmodule")
    s = s[:i] + """    always @(posedge clk) begin
        if (!rst_n) begin
            step <= 5'd24;
            done <= 1'b0;
            result <= 12'sd0;
        end else begin
            step <= idle ? {~start, ~start, 3'd0} : step + 5'd1;
            done <= round_step;
            if (round_step) begin
                if (invalid || overflow) result <= 12'sd0;
                else result <= signed_result;
            end else if (shift) result <= {result[10:0], 1'b0};
        end
    end
""" + s[j:]
    return s
open("candidates/c06_dq19_flip_step.v", "w").write(c06(G))
