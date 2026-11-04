/*
Jinyuan Zhao
Exponent LUT (softmax weight)
*/

/*
Turns a score into a weight:

    W ≈ 255 · e^((S - M) / 2),   D = M - S >= 0

The proposal gets there with the 23/32 trick (see exp_weight() in
python/src/attention_model.py): A = 23·D, n = A >> 5, r = (A >> 1) & 0xF,
W = round(T[r] >> n), with T[r] = round(255 · 2^(-r/16)).

BUT scores are whole numbers, so D is a whole number, and once D >= 13
that formula always gives 0. It only ever produces 13 different answers.
So we skip the ×23, the split and the shifter and just store the 13
answers, indexed by D. Same output, about 60% fewer gates.

    D :  0   1   2   3   4   5   6  7  8  9 10 11 12 | 13+
    W : 255 158 94  59  35  22  13  8  5  3  2  1  1 |  0

Checked against exp_weight() on every valid (M, S) pair:
test/blocks/test_exp_lut.py (115,921 cases).

NOTE: this holds for any integer scores, INT4 or INT8. Only the width
of M and S changes. If someone ever changes the /2 scaling, regenerate
the table from exp_weight().

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
    input  wire signed [9:0] M,       // final maximum score
    input  wire signed [9:0] S,       // this token's score
    output reg               done,
    output reg         [7:0] W        // 0 to 255, UNSIGNED
);

// D = M - S, one extra bit so a negative result is visible in diff[10]
wire signed [10:0] diff = {M[9], M} - {S[9], S};

reg [7:0] weight;
always @(*) begin
    if (diff[10]) begin
        weight = 8'd255;              // M < S: clamp to D = 0
    end else if (diff[9:4] != 6'd0) begin
        weight = 8'd0;                // D >= 16: way too far behind
    end else begin
        case (diff[3:0])
            4'd0:  weight = 8'd255;
            4'd1:  weight = 8'd158;
            4'd2:  weight = 8'd94;
            4'd3:  weight = 8'd59;
            4'd4:  weight = 8'd35;
            4'd5:  weight = 8'd22;
            4'd6:  weight = 8'd13;
            4'd7:  weight = 8'd8;
            4'd8:  weight = 8'd5;
            4'd9:  weight = 8'd3;
            4'd10: weight = 8'd2;
            4'd11: weight = 8'd1;
            4'd12: weight = 8'd1;
            default: weight = 8'd0;   // D = 13, 14, 15
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
