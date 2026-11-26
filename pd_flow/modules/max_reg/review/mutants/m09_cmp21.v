// mutant m09_cmp21: compare done on 21 bits (bit 21 dropped, bit 20 treated as sign)
module max_reg (
    input  wire              clk,
    input  wire              first,
    input  wire              en,
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);
wire signed [20:0] s21 = S_in[20:0], m21 = M[20:0];
always @(posedge clk) if (en && (first || s21 > m21)) M <= S_in;
endmodule
