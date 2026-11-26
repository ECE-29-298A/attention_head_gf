// mutant m23_sub_overflow: compare by 22-bit subtraction sign (overflow not handled)
module max_reg (
    input  wire              clk,
    input  wire              first,
    input  wire              en,
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);
wire signed [21:0] d = M - S_in;
always @(posedge clk) if (en && (first || d[21])) M <= S_in;
endmodule
