/*
Jinyuan Zhao
Max comparator
Phase 2 candidate c10: majority ripple with tie don't-care: c[1] = S_in[0] (bit-0 stage removed)
*/

module max_reg (
    input  wire              clk,
    input  wire              first,   // first score of the query: take it unconditionally
    input  wire              en,      // a finished score is on S_in this tick
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);

// c[i+1] = 1 when S_in[i:0] > M[i:0] (unsigned), or either value when S_in[i:0] == M[i:0]
// (a tie loads the value M already holds, so the result is unobservable).
wire [21:1] c;
assign c[1] = S_in[0];
genvar i;
generate for (i = 1; i < 21; i = i + 1) begin : g_cmp
    assign c[i+1] = (S_in[i] & ~M[i]) | ((S_in[i] | ~M[i]) & c[i]);
end endgenerate
// Sign bit (offset binary: S_in[21] = 0 is the larger half).
wire gt = (~S_in[21] & M[21]) | (~(S_in[21] ^ M[21]) & c[21]);
wire load = en && (first || gt);

always @(posedge clk) begin
    if (load) M <= S_in;
end

endmodule
