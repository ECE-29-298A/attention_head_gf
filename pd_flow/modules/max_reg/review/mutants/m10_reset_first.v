// mutant m10_reset_first: added clear on first while en = 0 (reset-like, uses existing input)
module max_reg (
    input  wire              clk,
    input  wire              first,
    input  wire              en,
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);
always @(posedge clk) if (en && (first || S_in > M)) M <= S_in; else if (first) M <= 22'd0;
endmodule
