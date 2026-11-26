// mutant m22_minneg_tie: MINNEG over MAXPOS wrongly loads (overflow-style compare fault on one pair)
module max_reg (
    input  wire              clk,
    input  wire              first,
    input  wire              en,
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);
wire gt = (S_in > M) || (S_in == 22'h200000 && M == 22'h1FFFFF);
always @(posedge clk) if (en && (first || gt)) M <= S_in;
endmodule
