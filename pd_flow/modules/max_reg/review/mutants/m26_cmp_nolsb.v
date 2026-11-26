// mutant m26_cmp_nolsb: compare ignores bit 0 (S_in = M+1 with even M holds)
module max_reg (
    input  wire              clk,
    input  wire              first,
    input  wire              en,
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);
wire gt = $signed(S_in[21:1]) > $signed(M[21:1]);
always @(posedge clk) if (en && (first || gt)) M <= S_in;
endmodule
