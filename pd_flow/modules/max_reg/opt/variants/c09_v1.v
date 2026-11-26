/*
Jinyuan Zhao
Max comparator
Phase 2 candidate c09: hand-written LSB-first majority ripple compare, cin 1 (ge)
*/

module max_reg (
    input  wire              clk,
    input  wire              first,   // first score of the query: take it unconditionally
    input  wire              en,      // a finished score is on S_in this tick
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);

// c[i+1] = 1 when S_in[i:0] > M[i:0] (unsigned): majority(S_in[i], ~M[i], c[i]).
wire [21:0] c;
assign c[0] = 1'b1;
genvar i;
generate for (i = 0; i < 21; i = i + 1) begin : g_cmp
    assign c[i+1] = (S_in[i] & ~M[i]) | ((S_in[i] | ~M[i]) & c[i]);
end endgenerate
// Sign bit (offset binary: S_in[21] = 0 is the larger half).
wire gt = (~S_in[21] & M[21]) | (~(S_in[21] ^ M[21]) & c[21]);
wire load = en && (gt || first);

always @(posedge clk) begin
    if (load) M <= S_in;
end

endmodule
