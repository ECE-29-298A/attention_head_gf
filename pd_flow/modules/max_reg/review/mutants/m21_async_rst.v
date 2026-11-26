// mutant m21_async_rst: async clear on first (no new port)
module max_reg (
    input  wire              clk,
    input  wire              first,
    input  wire              en,
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);
always @(posedge clk or posedge first) if (first && !en) M <= 22'd0; else if (en && (first || S_in > M)) M <= S_in;
endmodule
