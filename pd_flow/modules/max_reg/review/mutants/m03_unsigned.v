// mutant m03_unsigned: unsigned compare
module max_reg (
    input  wire              clk,
    input  wire              first,
    input  wire              en,
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);
always @(posedge clk) if (en && (first || $unsigned(S_in) > $unsigned(M))) M <= S_in;
endmodule
