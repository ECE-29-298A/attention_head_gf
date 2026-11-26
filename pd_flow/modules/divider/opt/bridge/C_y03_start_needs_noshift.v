`default_nettype none

// Signed attention normalization: round(16 * sum_in / denominator), a 12-bit
// code (INT8 plus 4 fractional bits), nearest with ties away from zero.
// Matches Python divide_round (out_frac = 4) on its domain.
// 23 restoring-division steps + 1 round/sign step after the accepted start.
// Inputs are latched when start && !busy. Starts while busy are ignored.
// done pulses for one cycle; result holds until completion of the next request,
// except that shift moves it left by one bit, taking in 0 (a serial output, MSB
// first, on result[11]). A completing division overrides a shift in the same cycle.
// Invalid requests (zero denominator, sum=-524288, or rounded result outside
// signed 12-bit range) complete with result=0 at the normal latency. Valid INT8
// attention cannot produce these requests. This is not saturating arithmetic.
// CHECK_INVALID = 0 drops the invalid/overflow detection. Use it only when the
// caller guarantees denominator > 0, sum_in != -524288 and an in-range result
// (true for the attention controller: L >= 255 and the result is an average of INT8).
module divider #(parameter LATCH_DENOMINATOR = 1, parameter CHECK_INVALID = 1) (
    input  wire              clk,
    input  wire              rst_n,       // Synchronous active-low reset; aborts operation.
    input  wire              start,
    input  wire signed [19:0] sum_in,      // Weighted sum O_i.
    input  wire        [11:0] denominator, // Weight sum L; must be positive.
    input  wire              shift,
    output wire              obs_lg, obs_lc,
    output wire        [4:0] obs_ph,
    output wire       [18:0] obs_dq,
    output wire       [11:0] obs_rm, obs_dv,
    output wire              obs_ng, obs_iv, obs_sn,
    output wire              busy,
    output reg               done,
    output reg signed [11:0] result       // Weighted average of V, in 1/16 V steps.
);
    // phase: 0 idle, 1..23 divide steps 0..22, 24 round.
    reg [4:0] phase;
    wire idle = phase == 5'd0;
    wire round_step = phase == 5'd24;
    reg [18:0] dq; // Starts as abs(O); dividend bits leave at the top, quotient bits enter at the bottom.
    reg [11:0] remainder_value;
    wire [11:0] divisor;
    if (LATCH_DENOMINATOR) begin : g_divisor
        reg [11:0] saved_divisor;
        always @(posedge clk)
            if (idle) saved_divisor <= denominator;
        assign divisor = saved_divisor;
    end else begin : g_direct_divisor
        // Integration contract: denominator stays stable from start to done.
        assign divisor = denominator;
    end
    reg negative, invalid_r;
    wire invalid = CHECK_INVALID ? invalid_r : 1'b0;

    wire [18:0] magnitude = sum_in[19] ? (~sum_in[18:0] + 19'd1) : sum_in[18:0];
    // The round step uses the same subtractor to compare 2*remainder with L.
    // Steps 19..22 take the four zero LSBs of 16*abs(O); ROUND (step 23) takes 0 as well.
    wire dividend_done = phase[4] & (phase[3] | phase[2]); // phase >= 20
    wire [12:0] trial = {remainder_value, !dividend_done && dq[18]};
    wire [13:0] difference = {1'b0, trial} - {2'b0, divisor};
    wire subtract = !difference[13];
    wire [11:0] next_remainder = subtract ? difference[11:0] : trial[11:0];
    // Quotient bits enter pre-complemented when negative (never read back as dividend bits).
    wire [18:0] next_dq = {dq[17:0], subtract ^ negative};
    // Overflow (CHECK_INVALID only): the 11 high quotient bits (steps 0..10) no longer stay in dq.
    wire high_quotient;
    if (CHECK_INVALID) begin : g_high_quotient
        reg seen;
        always @(posedge clk) seen <= idle ? 1'b0 : seen | (subtract && phase < 5'd12);
        assign high_quotient = seen;
    end else begin : g_no_high_quotient
        assign high_quotient = 1'b0;
    end
    wire [12:0] rounded = {1'b0, dq[11:0] ^ {12{negative}}} + {12'b0, subtract};
    // -(q + s) = ~q + !s, so one incrementer rounds and applies the sign.
    wire [11:0] signed_result = dq[11:0] + {11'b0, subtract ^ negative};
    wire overflow = CHECK_INVALID ? (high_quotient || (negative ? rounded > 13'd2048 : rounded > 13'd2047)) : 1'b0;
    assign busy = !idle;

    // Only the ROUND state consumes these registers. IDLE overwrites them
    // on the same edge that accepts start, so idle and reset need no holds.
    always @(posedge clk) begin
        dq <= idle ? magnitude : next_dq;
        remainder_value <= idle ? 12'd0 : next_remainder;
        if (idle) begin
            negative <= sum_in[19];
            invalid_r <= denominator == 12'd0 || sum_in == 20'sh80000;
        end
    end

    always @(posedge clk) begin
        if (!rst_n) begin
            phase <= 5'd0;
            done <= 1'b0;
            result <= 12'sd0;
        end else begin
            phase <= idle ? {4'd0, start & ~shift} : // NEGCTL
                     round_step ? 5'd0 : phase + 5'd1;
            done <= round_step;
            if (round_step) begin
                if (invalid || overflow) result <= 12'sd0;
                else result <= signed_result;
            end else if (shift) result <= {result[10:0], 1'b0};
        end
    end
    // ---- observers (proof bridge only)
    assign obs_lg = 1'b1;
    assign obs_lc = phase <= 5'd24;
    assign obs_ph = phase;
    assign obs_dq = busy ? dq : 19'd0;
    assign obs_rm = busy ? remainder_value : 12'd0;
    assign obs_dv = busy ? divisor : 12'd0;
    assign obs_ng = busy & negative;
    assign obs_iv = busy & invalid_r;
    assign obs_sn = busy & high_quotient;
endmodule

`default_nettype wire
