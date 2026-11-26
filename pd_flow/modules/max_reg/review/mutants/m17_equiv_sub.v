// mutant m17_equiv_sub: equivalent rewrite: sign of 23-bit difference
module max_reg (
    input  wire              clk,
    input  wire              first,
    input  wire              en,
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);
wire signed [22:0] d = {M[21], M} - {S_in[21], S_in};
always @(posedge clk) if (en && (first || d[22])) M <= S_in;
endmodule
