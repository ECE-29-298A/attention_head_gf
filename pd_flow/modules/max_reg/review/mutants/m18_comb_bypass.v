// mutant m18_comb_bypass: combinational bypass: M shows S_in in the same cycle on a first load
module max_reg (
    input  wire              clk,
    input  wire              first,
    input  wire              en,
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);
reg signed [21:0] q;
always @(posedge clk) if (en && (first || S_in > q)) q <= S_in;
always @* M = (en && first) ? S_in : q;
endmodule
