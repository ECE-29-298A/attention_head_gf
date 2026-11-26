// mutant m06_prec_swap: en/first precedence swapped: first loads without en
module max_reg (
    input  wire              clk,
    input  wire              first,
    input  wire              en,
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);
always @(posedge clk) if (first || (en && S_in > M)) M <= S_in;
endmodule
