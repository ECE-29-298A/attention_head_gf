// mutant m08_stuck0_b13: stuck-at-0 on stored bit 13
module max_reg (
    input  wire              clk,
    input  wire              first,
    input  wire              en,
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);
always @(posedge clk) if (en && (first || S_in > M)) M <= {S_in[21:14], 1'b0, S_in[12:0]};
endmodule
