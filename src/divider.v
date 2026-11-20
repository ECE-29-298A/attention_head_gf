`default_nettype none

// Signed attention normalization: round(16 * sum_in / denominator), a 12-bit
// code (INT8 plus 4 fractional bits), nearest with ties away from zero.
// Matches Python divide_round (out_frac = 4) on its domain.
// 23 restoring-division steps + 1 round/sign step after the accepted start.
// sum_in is latched when start is accepted in idle; starts while dividing are
// ignored. denominator must stay stable from start to done. done pulses for one
// cycle; result is valid from done until the next start (the quotient register
// holds it). Requires denominator > 0 and a result that fits 12 bits (always
// true for INT8 attention: L >= 255 and |O / L| <= 128). No checking is done.
module divider (
    input  wire               clk,
    input  wire               rst_n,       // Synchronous active-low reset; aborts operation.
    input  wire               start,
    input  wire signed [19:0] sum_in,      // Weighted sum O_i.
    input  wire        [11:0] denominator, // Weight sum L; must be positive.
    output reg                done,
    output wire signed [11:0] result       // Weighted average of V, in 1/16 V steps.
);
    localparam [1:0] IDLE = 2'd0, DIVIDE = 2'd1, ROUND = 2'd2;
    reg [1:0] state;
    reg [22:0] quotient; // abs(O) * 16 (< 2^23), shifted into the quotient in place
    reg [11:0] remainder_value;
    reg [4:0] step;
    reg negative;

    wire [18:0] magnitude = sum_in[19] ? (~sum_in[18:0] + 19'd1) : sum_in[18:0];
    // In ROUND the same subtractor compares 2*remainder with L (quotient[22] is 0 there).
    wire [12:0] trial = {remainder_value, quotient[22]};
    wire [13:0] difference = {1'b0, trial} - {2'b0, denominator};
    wire subtract = !difference[13];
    wire [11:0] next_remainder = subtract ? difference[11:0] : trial[11:0];
    wire [11:0] rounded = quotient[11:0] + {11'b0, subtract};
    assign result = quotient[11:0];

    always @(posedge clk) begin
        if (state == IDLE) begin
            if (start) quotient <= {magnitude, 4'b0};
            negative <= sum_in[19];
        end else if (state == ROUND) quotient[11:0] <= negative ? -rounded : rounded;
        else quotient <= {quotient[21:0], subtract};
        remainder_value <= state == IDLE ? 12'd0 : next_remainder;
        step <= state == IDLE ? 5'd0 : step + 5'd1;
        done <= state == ROUND;
    end

    always @(posedge clk)
        if (!rst_n) state <= IDLE;
        else case (state)
            IDLE: if (start) state <= DIVIDE;
            DIVIDE: if (step == 5'd22) state <= ROUND;
            default: state <= IDLE;
        endcase
endmodule

`default_nettype wire
