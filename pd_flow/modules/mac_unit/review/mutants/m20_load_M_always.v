// mutant m20_load_M_always: load ignores subtract: pass 1 also starts from M
// Score MAC and V accumulator sharing one 22-bit ripple adder and one shifter.
// They never run in the same cycle: accum_mode = 0 is SCORE_MAC, 1 otherwise.
//
// Score: load sets S to 0 (subtract = 0) or M (subtract = 1); each score_en
// cycle adds or subtracts qi * (one bit of ki), so pass 2 ends with D = M - S.
// Accumulate: OUTPUTS 20-bit sums form a ring that turns every clock, so the
// head O0 always holds component `sel` (the caller's free-running phase). Each
// accum_en cycle adds W * (one bit of v) to the head. Bits come MSB first (as
// they leave the flash), so the first token's bit 7 loads instead of adding.
// While scoring, the ring bypasses the busy adder and keeps its sums.
module mac_unit #(parameter OUTPUTS = 8) ( // 2, 4 or 8
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
    input  wire [$clog2(OUTPUTS)-1:0] sel,
    input  wire signed [7:0] v,
    input  wire        [2:0] bit_sel,
    output reg  signed [21:0] S,
    output reg        [11:0] L,
    output wire signed [19:0] O0 // |O| <= 16 * 255 * 128 = 522240
);
    // ring[19:0] is the head O0; the tail takes the head's new sum (or the head
    // unchanged while scoring). No enable and no reset: plain flops.
    reg [20*OUTPUTS-1:0] ring;
    assign O0 = ring[19:0];
    wire [8:0] x = accum_mode ? {1'b0, W} : {qi[7], qi};
    wire bit_on = accum_mode ? (accum_en && v[bit_sel]) : ki[bit_sel];
    wire top = bit_sel == 3'd7;
    wire neg = accum_mode ? (accum_en && top) : (top ^ subtract);
    wire [21:0] term = bit_on ? ({{13{x[8]}}, x} << bit_sel) : 22'd0;
    wire load_o = accum_en && first && top;
    wire [21:0] a = accum_mode ? (load_o ? 22'd0 : {{2{O0[19]}}, O0}) : S;
    wire [21:0] sum;
    ripple_add #(.N(22)) adder (.a(a), .b(neg ? ~term : term), .cin(neg), .s(sum));
    wire [11:0] L_next;
    ripple_add #(.N(12)) l_adder (.a(first ? 12'd0 : L), .b({4'b0, W}), .cin(1'b0), .s(L_next));
    wire _unused = &{sum[21:20], 1'b0};
    always @(posedge clk) begin
        ring <= {accum_mode ? sum[19:0] : O0, ring[20*OUTPUTS-1:20]};
        if (accum_en && ~|sel && bit_sel == 3'd0) L <= L_next;
        if (load) S <= M;
        else if (score_en) S <= $signed(sum);
    end
endmodule
