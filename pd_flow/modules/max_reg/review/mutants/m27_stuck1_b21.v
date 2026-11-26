// mutant m27_stuck1_b21: stuck-at-1 on stored sign bit 21
module max_reg (
    input  wire              clk,
    input  wire              first,
    input  wire              en,
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);
always @(posedge clk) if (en && (first || S_in > M)) M <= {1'b1, S_in[20:0]};
endmodule
