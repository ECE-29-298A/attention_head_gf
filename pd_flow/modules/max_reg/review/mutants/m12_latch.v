// mutant m12_latch: transparent-high latch instead of a flop
module max_reg (
    input  wire              clk,
    input  wire              first,
    input  wire              en,
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);
always @* if (clk && en && (first || S_in > M)) M = S_in;
endmodule
