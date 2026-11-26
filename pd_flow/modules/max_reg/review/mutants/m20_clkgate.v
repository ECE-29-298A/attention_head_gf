// mutant m20_clkgate: clock-gated (latch-based ICG style): functionally correct; contract rejects by R11
module max_reg (
    input  wire              clk,
    input  wire              first,
    input  wire              en,
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);
wire ld = en && (first || S_in > M);
reg ldl; always @* if (!clk) ldl = ld;
wire gclk = clk & ldl;
always @(posedge gclk) M <= S_in;
endmodule
