`default_nettype none

// Signed attention normalization: round(16 * sum_in / denominator),
// nearest with ties away from zero. Matches Python divide_round on its domain.
// 19 restoring-division steps + 1 round/sign step after the accepted start.
// Inputs are latched when start && !busy. Starts while busy are ignored.
// done pulses for one cycle; result holds until completion of the next request.
// Invalid requests (zero denominator, sum=-32768, or rounded result outside
// signed 8-bit range) complete with result=0 at the normal latency. Valid INT4
// attention cannot produce these requests. This is not saturating arithmetic.
module divider (
    input  wire              clk,
    input  wire              rst_n,       // Synchronous active-low reset; aborts operation.
    input  wire              start,
    input  wire signed [15:0] sum_in,      // Weighted sum O_i.
    input  wire        [11:0] denominator, // Weight sum L; must be positive.
    output wire              busy,
    output reg               done,
    output reg signed  [7:0] result       // Real value = signed code / 16.
);
    localparam [1:0] IDLE = 2'd0, DIVIDE = 2'd1, ROUND = 2'd2;
    reg [1:0] state;
    reg [18:0] quotient; // Starts as 16*abs(O); shifted into a quotient in place.
    reg [11:0] remainder_value, divisor;
    reg [4:0] step;
    reg negative, invalid;

    wire [15:0] magnitude = sum_in[15] ? (~sum_in + 16'd1) : sum_in;
    wire [12:0] trial = {remainder_value, quotient[18]};
    wire subtract = trial >= {1'b0, divisor};
    // The 13-bit comparison decides subtraction. For valid L, the new remainder
    // is < L <= 4095, so its low 12-bit subtraction contains the complete result.
    wire [11:0] next_remainder = trial[11:0] - (subtract ? divisor : 12'd0);
    wire [18:0] next_quotient = {quotient[17:0], subtract};
    wire round_up = {remainder_value, 1'b0} >= {1'b0, divisor};
    // Extra bit prevents carry-out during rounding from silently wrapping.
    wire [19:0] rounded = {1'b0, quotient} + (round_up ? 20'd1 : 20'd0);
    wire overflow = negative ? rounded > 20'd128 : rounded > 20'd127;
    assign busy = state != IDLE;

    always @(posedge clk) begin
        if (!rst_n) begin
            state <= IDLE;
            quotient <= 19'd0;
            remainder_value <= 12'd0;
            divisor <= 12'd0;
            step <= 5'd0;
            negative <= 1'b0;
            invalid <= 1'b0;
            done <= 1'b0;
            result <= 8'sd0;
        end else begin
            done <= 1'b0;
            case (state)
                IDLE: if (start) begin
                    quotient <= {magnitude[14:0], 4'b0000};
                    remainder_value <= 12'd0;
                    divisor <= denominator;
                    negative <= sum_in[15];
                    invalid <= denominator == 12'd0 || magnitude[15];
                    step <= 5'd0;
                    state <= DIVIDE;
                end
                DIVIDE: begin
                    quotient <= next_quotient;
                    remainder_value <= next_remainder;
                    if (step == 5'd18) state <= ROUND;
                    else step <= step + 5'd1;
                end
                ROUND: begin
                    if (invalid || overflow) result <= 8'sd0;
                    else if (negative) result <= ~rounded[7:0] + 8'd1;
                    else result <= rounded[7:0];
                    done <= 1'b1;
                    state <= IDLE;
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule

`default_nettype wire
