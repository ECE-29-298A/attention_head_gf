// mutant m24_first_onlyhigh: first only overrides for non-negative S_in
module max_reg (
    input  wire              clk,
    input  wire              first,
    input  wire              en,
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);
always @(posedge clk) if (en && ((first && S_in[21] == 1'b0) || S_in > M)) M <= S_in;
endmodule
