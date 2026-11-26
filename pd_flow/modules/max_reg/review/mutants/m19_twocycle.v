// mutant m19_twocycle: two-cycle latency (extra pipeline stage; 44 flops)
module max_reg (
    input  wire              clk,
    input  wire              first,
    input  wire              en,
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);
reg signed [21:0] q;
always @(posedge clk) begin if (en && (first || S_in > M)) q <= S_in; else q <= M; M <= q; end
endmodule
