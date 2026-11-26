/*
Jinyuan Zhao
Max comparator
Phase 2 candidate c12: mux-chain ripple: c[i+1] = (S_in[i] ^ M[i]) ? S_in[i] : c[i], tie don't-care
*/

module max_reg (
    input  wire              clk,
    input  wire              first,   // first score of the query: take it unconditionally
    input  wire              en,      // a finished score is on S_in this tick
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);

wire [21:1] c;
assign c[1] = S_in[0];
genvar i;
generate for (i = 1; i < 21; i = i + 1) begin : g_cmp
    assign c[i+1] = (S_in[i] ^ M[i]) ? S_in[i] : c[i];
end endgenerate
wire gt = (S_in[21] ^ M[21]) ? M[21] : c[21];
wire load = en && (first || gt);

wire signed [21:0] M_next = load ? S_in : M;

always @(posedge clk) begin
    M <= M_next;
end

endmodule
