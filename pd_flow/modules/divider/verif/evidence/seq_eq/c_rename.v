`default_nettype none

// Signed attention normalization: round(16 * sum_in / denominator), a 12-bit
// code (INT8 plus 4 fractional bits), nearest with ties away from zero.
// Matches Python divide_round (out_frac = 4) on its domain.
// 23 restoring-division steps + 1 round/sign count_q after the accepted start.
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
// seq_eq self-check: cosmetic rewrite of the golden. Every register renamed, the sign bit
// stored complemented. Equivalent; eqy_rtl cannot match it, seq_eq with lemmas proves it.
module divider #(parameter LATCH_DENOMINATOR = 1, parameter CHECK_INVALID = 1) (
    input  wire              clk,
    input  wire              rst_n,       // Synchronous active-low reset; aborts operation.
    input  wire              start,
    input  wire signed [19:0] sum_in,      // Weighted sum O_i.
    input  wire        [11:0] denominator, // Weight sum L; must be positive.
    input  wire              shift,
    output wire              busy,
    output reg               done,
    output reg signed [11:0] result       // Weighted average of V, in 1/16 V steps.
);
    localparam [1:0] IDLE = 2'd0, DIVIDE = 2'd1, ROUND = 2'd2;
    reg [1:0] fsm_q;
    reg [22:0] dividend_q; // Starts as abs(O) * 16 (< 2^23 when valid); shifted into a dividend_q in place.
    reg [11:0] rem_q;
    wire [11:0] divisor;
    if (LATCH_DENOMINATOR) begin : g_divisor
        reg [11:0] div_q;
        always @(posedge clk)
            if (fsm_q == IDLE) div_q <= denominator;
        assign divisor = div_q;
    end else begin : g_direct_divisor
        // Integration contract: denominator stays stable from start to done.
        assign divisor = denominator;
    end
    reg [4:0] count_q;
    reg positive_q, bad_q; // negative stored complemented
    wire negative = !positive_q;
    wire invalid = CHECK_INVALID ? bad_q : 1'b0;

    wire [18:0] magnitude = sum_in[19] ? (~sum_in[18:0] + 19'd1) : sum_in[18:0];
    // The round count_q uses the same subtractor to compare 2*remainder with L.
    wire [12:0] trial = {rem_q, (fsm_q != ROUND) && dividend_q[22]};
    wire [13:0] difference = {1'b0, trial} - {2'b0, divisor};
    wire subtract = !difference[13];
    wire [11:0] next_remainder = subtract ? difference[11:0] : trial[11:0];
    wire [22:0] next_quotient = {dividend_q[21:0], subtract};
    wire [12:0] rounded = {1'b0, dividend_q[11:0]} + {12'b0, subtract};
    // -(q + s) = ~q + !s, so one incrementer rounds and applies the sign.
    wire [11:0] signed_result = (dividend_q[11:0] ^ {12{negative}}) + {11'b0, subtract ^ negative};
    wire overflow = CHECK_INVALID ? (|dividend_q[22:12] || (negative ? rounded > 13'd2048 : rounded > 13'd2047)) : 1'b0;
    assign busy = fsm_q != IDLE;

    // Only the ROUND fsm_q consumes these registers. IDLE overwrites them
    // on the same edge that accepts start, so idle and reset need no holds.
    always @(posedge clk) begin
        dividend_q <= fsm_q == IDLE ? {magnitude, 4'b0} : next_quotient;
        rem_q <= fsm_q == IDLE ? 12'd0 : next_remainder;
        count_q <= fsm_q == IDLE ? 5'd0 : count_q + 5'd1;
        if (fsm_q == IDLE) begin
            positive_q <= !sum_in[19];
            bad_q <= denominator == 12'd0 || sum_in == 20'sh80000;
        end
    end

    always @(posedge clk) begin
        if (!rst_n) begin
            fsm_q <= IDLE;
            done <= 1'b0;
            result <= 12'sd0;
        end else begin
            done <= 1'b0;
            if (shift) result <= {result[10:0], 1'b0};
            case (fsm_q)
                IDLE: if (start) fsm_q <= DIVIDE;
                DIVIDE: if (count_q == 5'd22) fsm_q <= ROUND;
                ROUND: begin
                    if (invalid || overflow) result <= 12'sd0;
                    else result <= signed_result;
                    done <= 1'b1;
                    fsm_q <= IDLE;
                end
                default: fsm_q <= IDLE;
            endcase
        end
    end
endmodule

`default_nettype wire
