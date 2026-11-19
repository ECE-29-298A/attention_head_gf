`default_nettype none

// Signed attention normalization: round(sum_in / denominator), an INT8 code,
// nearest with ties away from zero. Matches Python divide_round on its domain.
// 19 restoring-division steps + 1 round/sign step after the accepted start.
// Inputs are latched when start && !busy. Starts while busy are ignored.
// done pulses for one cycle; result holds until completion of the next request.
// Invalid requests (zero denominator, sum=-524288, or rounded result outside
// signed 8-bit range) complete with result=0 at the normal latency. Valid INT8
// attention cannot produce these requests. This is not saturating arithmetic.
module divider (
    input  wire              clk,
    input  wire              rst_n,       // Synchronous active-low reset; aborts operation.
    input  wire              start,
    input  wire signed [19:0] sum_in,      // Weighted sum O_i.
    input  wire        [11:0] denominator, // Weight sum L; must be positive.
    output wire              busy,
    output reg               done,
    output reg signed  [7:0] result       // INT8 weighted average of V.
);
    localparam [1:0] IDLE = 2'd0, DIVIDE = 2'd1, ROUND = 2'd2;
    reg [1:0] state;
    reg [18:0] quotient; // Starts as abs(O) (< 2^19 when valid); shifted into a quotient in place.
    reg [11:0] remainder_value, divisor;
    reg [4:0] step;
    reg negative, invalid;

    wire [18:0] magnitude = sum_in[19] ? (~sum_in[18:0] + 19'd1) : sum_in[18:0];
    // The round step uses the same subtractor to compare 2*remainder with L.
    wire [12:0] trial = {remainder_value, (state != ROUND) && quotient[18]};
    wire [13:0] difference = {1'b0, trial} - {2'b0, divisor};
    wire subtract = !difference[13];
    wire [11:0] next_remainder = subtract ? difference[11:0] : trial[11:0];
    wire [18:0] next_quotient = {quotient[17:0], subtract};
    wire [8:0] rounded = {1'b0, quotient[7:0]} + {8'b0, subtract};
    wire overflow = |quotient[18:8] || (negative ? rounded > 9'd128 : rounded > 9'd127);
    assign busy = state != IDLE;

    always @(posedge clk) begin
        if (state == IDLE && start) begin
            quotient <= magnitude;
            remainder_value <= 12'd0;
            divisor <= denominator;
            negative <= sum_in[19];
            invalid <= denominator == 12'd0 || sum_in == 20'sh80000;
            step <= 5'd0;
        end else if (state == DIVIDE) begin
            quotient <= next_quotient;
            remainder_value <= next_remainder;
            step <= step + 5'd1;
        end
    end

    always @(posedge clk) begin
        if (!rst_n) begin
            state <= IDLE;
            done <= 1'b0;
            result <= 8'sd0;
        end else begin
            done <= 1'b0;
            case (state)
                IDLE: if (start) state <= DIVIDE;
                DIVIDE: if (step == 5'd18) state <= ROUND;
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
