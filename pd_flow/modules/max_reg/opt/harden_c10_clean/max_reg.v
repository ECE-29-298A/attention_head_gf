/*
Jinyuan Zhao
Max comparator
*/

module max_reg (
    input  wire              clk,
    input  wire              first,   // first score of the query: take it unconditionally
    input  wire              en,      // a finished score is on S_in this tick
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);

/*
Every time we finished a score (from score_mac), max_reg compares to the biggest one it's seen so far and keep whichever one is larger.
After the last key it will hold M (top score). The first score is loaded
directly, so no reset or sentinel value is needed.

Phase 2 (area): the signed compare S_in > M is written as an LSB-first majority ripple.
c[i+1] = maj(S_in[i], ~M[i], c[i]) is 1 when S_in[i:0] > M[i:0] (unsigned). On a tie the
result does not matter (loading S_in == M keeps M), so the bit-0 stage is dropped:
c[1] = S_in[0]. The sign bit is compared in offset binary. EQY-proven equivalent to
`en && (first || S_in > M)` (pd_flow/modules/max_reg/opt/OPTIMIZATION.md).
*/
wire [21:1] c;
assign c[1] = S_in[0];
genvar i;
generate for (i = 1; i < 21; i = i + 1) begin : g_cmp
    assign c[i+1] = (S_in[i] & ~M[i]) | ((S_in[i] | ~M[i]) & c[i]);
end endgenerate
wire gt = (~S_in[21] & M[21]) | (~(S_in[21] ^ M[21]) & c[21]);

always @(posedge clk) begin
    if (en) begin
        if (first || gt) M <= S_in;
    end
end

endmodule
