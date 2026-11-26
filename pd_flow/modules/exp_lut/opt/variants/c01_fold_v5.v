/*
Jinyuan Zhao
Exponent LUT (softmax weight)
*/

/*
Turns a score into a weight:

    W ≈ 255 · e^(-D' / 4),   D = M - S >= 0,   D' = round(D / 2^shift)

Scores are raw 64-dim INT8 dot products, far bigger than the table's range.
The host picks shift (0..15) from its Q/K quantization scales so that one unit
of D' is 0.25 nat. D' rounds to nearest (add 2^(shift-1), then shift):
truncating instead cost 1.3% next-token agreement on SmolLM. shift = 0 looks
up D directly. Must match exp_weight(..., score_shift, score_round=True).

D' is a whole number, and once D' >= 25 the weight rounds to 0. That means there
are only 25 possible answers, so we just store them: W = round(255 · e^(-D'/4)).

    D':  0   1   2   3   4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 | 25+
    W : 255 199 155 120 94 73 57 44 35 27 21 16 13 10  8  6  5  4  3  2  2  1  1  1  1 |  0

(Originally /2 with 13 entries. /4 halves the score step, the largest error
source on real SmolLM attention: see python/smollm_compare.py.)

Must match exp_weight() / EXP_TABLE in python/src/attention_model.py.
Checked at every shift over the score range plus random pairs: test/blocks/test_exp_lut.py.

NOTE: this holds for any integer scores. If someone ever changes the /4 scaling,
regenerate the table from exp_table() in the Python model.

Handshake (matches attention_controller):
    start: one-cycle pulse, M, S and shift valid on that edge
    done:  high for exactly one cycle, the cycle AFTER start
    W:     valid when done is high, held until the next start

With REGISTERED = 0 the block is combinational: W follows D and shift, and
done = start. The controller uses this because it already holds D and shift
stable for the whole accumulate step.

The controller computes D = M - S itself (its pass-2 score starts at M and
subtracts), so this block has no subtractor. D is never negative.
*/

module exp_lut #(parameter REGISTERED = 1) (
    input  wire              clk,
    input  wire              rst_n,
    input  wire              start,
    input  wire        [21:0] D,      // M - S >= 0 (< 2^21 for INT8 scores)
    input  wire        [3:0] shift,   // D is rounded and shifted right by this; sampled on start
    output wire              done,
    output wire        [7:0] W        // 0 to 255, UNSIGNED
);

// Rounding folded into the table: aligned = floor(2D / 2^shift) (6-bit window),
// D' = (aligned + 1) >> 1, so the table is indexed by aligned directly (49 non-zero entries).
wire [20:0] delta_guard = {D[19:0], 1'b0};
wire [12:0] stage8 = shift[3] ? delta_guard[20:8] : delta_guard[12:0];
wire [8:0] stage4 = shift[2] ? stage8[12:4] : stage8[8:0];
wire [6:0] stage2 = shift[1] ? stage4[8:2] : stage4[6:0];
wire [5:0] aligned = shift[0] ? stage2[6:1] : stage2[5:0];
wire window_ovf = (|D[21:20]) |
    (!shift[3] & (|delta_guard[20:13])) |
    (!shift[2] & (|stage8[12:9])) |
    (!shift[1] & (|stage4[8:7])) |
    (!shift[0] & stage2[6]);

reg [7:0] weight;
always @(*) begin
    if (window_ovf) begin
        weight = 8'd0;
    end else begin
        case (aligned)
            6'd47, 6'd48: weight = 8'd1;
            6'd45, 6'd46: weight = 8'd1;
            6'd43, 6'd44: weight = 8'd1;
            6'd41, 6'd42: weight = 8'd1;
            6'd39, 6'd40: weight = 8'd2;
            6'd37, 6'd38: weight = 8'd2;
            6'd35, 6'd36: weight = 8'd3;
            6'd33, 6'd34: weight = 8'd4;
            6'd31, 6'd32: weight = 8'd5;
            6'd29, 6'd30: weight = 8'd6;
            6'd27, 6'd28: weight = 8'd8;
            6'd25, 6'd26: weight = 8'd10;
            6'd23, 6'd24: weight = 8'd13;
            6'd21, 6'd22: weight = 8'd16;
            6'd19, 6'd20: weight = 8'd21;
            6'd17, 6'd18: weight = 8'd27;
            6'd15, 6'd16: weight = 8'd35;
            6'd13, 6'd14: weight = 8'd44;
            6'd11, 6'd12: weight = 8'd57;
            6'd9, 6'd10: weight = 8'd73;
            6'd7, 6'd8: weight = 8'd94;
            6'd5, 6'd6: weight = 8'd120;
            6'd3, 6'd4: weight = 8'd155;
            6'd1, 6'd2: weight = 8'd199;
            6'd0: weight = 8'd255;
            default: weight = 8'd0;
        endcase
    end
end

if (REGISTERED) begin : g_registered
    reg done_r;
    reg [7:0] W_r;
    always @(posedge clk) begin
        if (!rst_n) begin
            done_r <= 1'b0;
            W_r    <= 8'd0;
        end else begin
            done_r <= start;
            if (start) begin
                W_r <= weight;
            end
        end
    end
    assign done = done_r;
    assign W = W_r;
end else begin : g_combinational
    assign done = start;
    assign W = weight;
    wire _unused = &{clk, rst_n, 1'b0};
end

endmodule
