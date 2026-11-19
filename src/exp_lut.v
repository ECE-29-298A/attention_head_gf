/*
Jinyuan Zhao
Exponent LUT (softmax weight)
*/

/*
Turns a score into a weight:

    W ≈ 255 · e^((S - M) / 4),   D = M - S >= 0

One score unit is 0.25 nat. Scores are whole numbers, so D is a whole number,
and once D >= 25 the weight rounds to 0. That means there are only 25 possible
answers, so we just store them: W = round(255 · e^(-D/4)), indexed by D.

    D :  0   1   2   3   4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 | 25+
    W : 255 199 155 120 94 73 57 44 35 27 21 16 13 10  8  6  5  4  3  2  2  1  1  1  1 |  0

(Originally /2 with 13 entries. /4 halves the score step, the largest error
source on real SmolLM attention: see python/smollm_compare.py.)

Must match exp_weight() / EXP_TABLE in python/src/attention_model.py.
Checked at D = 0..32 over the score range plus random pairs: test/blocks/test_exp_lut.py.

NOTE: this holds for any integer scores. If someone ever changes the /4 scaling,
regenerate the table from exp_table() in the Python model.

Handshake (matches attention_controller):
    start: one-cycle pulse, M and S valid on that edge
    done:  high for exactly one cycle, the cycle AFTER start
    W:     valid when done is high, held until the next start

If M < S (contract violation, the controller always passes the real
max), D is treated as 0, so W = 255.
*/

module exp_lut (
    input  wire              clk,
    input  wire              rst_n,
    input  wire              start,
    input  wire signed [17:0] M,      // final maximum score
    input  wire signed [17:0] S,      // this token's score
    output reg               done,
    output reg         [7:0] W        // 0 to 255, UNSIGNED
);

// D = M - S, one extra bit so a negative result is visible in diff[18]
wire signed [18:0] diff = {M[17], M} - {S[17], S};

reg [7:0] weight;
always @(*) begin
    if (diff[18]) begin
        weight = 8'd255;              // M < S: clamp to D = 0
    end else if (diff[17:5] != 13'd0) begin
        weight = 8'd0;                // D >= 32: way too far behind
    end else begin
        case (diff[4:0])
            5'd0:  weight = 8'd255;
            5'd1:  weight = 8'd199;
            5'd2:  weight = 8'd155;
            5'd3:  weight = 8'd120;
            5'd4:  weight = 8'd94;
            5'd5:  weight = 8'd73;
            5'd6:  weight = 8'd57;
            5'd7:  weight = 8'd44;
            5'd8:  weight = 8'd35;
            5'd9:  weight = 8'd27;
            5'd10: weight = 8'd21;
            5'd11: weight = 8'd16;
            5'd12: weight = 8'd13;
            5'd13: weight = 8'd10;
            5'd14: weight = 8'd8;
            5'd15: weight = 8'd6;
            5'd16: weight = 8'd5;
            5'd17: weight = 8'd4;
            5'd18: weight = 8'd3;
            5'd19: weight = 8'd2;
            5'd20: weight = 8'd2;
            5'd21: weight = 8'd1;
            5'd22: weight = 8'd1;
            5'd23: weight = 8'd1;
            5'd24: weight = 8'd1;
            default: weight = 8'd0;   // D = 25 .. 31
        endcase
    end
end

always @(posedge clk) begin
    if (!rst_n) begin
        done <= 1'b0;
        W    <= 8'd0;
    end else begin
        done <= start;
        if (start) begin
            W <= weight;
        end
    end
end

endmodule
