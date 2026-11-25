// Score MAC and V accumulator sharing one 22-bit ripple adder and one shifter.
// They never run in the same cycle: accum_mode = 0 is SCORE_MAC, 1 otherwise.
//
// Score: load sets S to 0 (subtract = 0) or M (subtract = 1); each score_en
// cycle adds or subtracts qi * (one bit of ki), so pass 2 ends with D = M - S.
// Accumulate: the two O registers form a ring that turns every clock, so O0
// always holds component `sel` (the caller's free-running phase). Each
// accum_en cycle adds W * (one bit of v) to the head; first-token bit 0 loads.
// While scoring, the ring bypasses the busy adder and keeps its sums.
module mac_unit (
    input  wire              clk,
    input  wire              accum_mode,
    // score side
    input  wire              load, subtract,
    input  wire signed [21:0] M,
    input  wire              score_en,
    input  wire signed [7:0] qi, ki,
    // accumulate side
    input  wire              first, accum_en,
    input  wire        [7:0] W,
    input  wire              sel,
    input  wire signed [7:0] v,
    input  wire        [2:0] bit_sel,
    output reg  signed [21:0] S,
    output reg        [11:0] L,
    output reg  signed [19:0] O0, O1 // |O| <= 16 * 255 * 128 = 522240
);
    wire [8:0] x = accum_mode ? {1'b0, W} : {qi[7], qi};
    wire bit_on = accum_mode ? (accum_en && v[bit_sel]) : ki[bit_sel];
    wire top = bit_sel == 3'd7;
    wire neg = accum_mode ? (accum_en && top) : (top ^ subtract);
    wire [21:0] term = bit_on ? ({{13{x[8]}}, x} << bit_sel) : 22'd0;
    wire load_o = accum_en && first && bit_sel == 3'd0;
    wire [21:0] a = accum_mode ? (load_o ? 22'd0 : {{2{O0[19]}}, O0}) : S;
    wire [21:0] sum;
    ripple_add #(.N(22)) adder (.a(a), .b(neg ? ~term : term), .cin(neg), .s(sum));
    wire [11:0] L_next;
    ripple_add #(.N(12)) l_adder (.a(first ? 12'd0 : L), .b({4'b0, W}), .cin(1'b0), .s(L_next));
    wire _unused = &{sum[21:20], 1'b0};
    always @(posedge clk) begin
        O0 <= O1;
        O1 <= accum_mode ? $signed(sum[19:0]) : O0;
        if (accum_en && !sel && bit_sel == 3'd0) L <= L_next;
        if (load) S <= subtract ? M : 22'sd0;
        else if (score_en) S <= $signed(sum);
    end
endmodule
