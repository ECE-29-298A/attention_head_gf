/*
Jinyuan Zhao
Max comparator
Phase 2 candidate c11: alternating-polarity majority ripple (inverting stages), tie don't-care at bit 0
*/

module max_reg (
    input  wire              clk,
    input  wire              first,   // first score of the query: take it unconditionally
    input  wire              en,      // a finished score is on S_in this tick
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);

// p[i] = c[i] for odd i, ~c[i] for even i, where c[i+1] = maj(S_in[i], ~M[i], c[i]).
// maj(a, b, c) = ~maj(~a, ~b, ~c), so each stage is one inverting majority.
wire [21:1] p;
assign p[1] = S_in[0];
genvar i;
generate for (i = 1; i < 21; i = i + 1) begin : g_cmp
    if (i % 2 == 1) begin : g_odd // p[i] = c[i] -> p[i+1] = ~c[i+1]
        assign p[i+1] = ~((S_in[i] & ~M[i]) | ((S_in[i] | ~M[i]) & p[i]));
    end else begin : g_even       // p[i] = ~c[i] -> p[i+1] = c[i+1] = ~maj(~S, M, ~c)
        assign p[i+1] = ~((~S_in[i] & M[i]) | ((~S_in[i] | M[i]) & p[i]));
    end
end endgenerate
wire c21 = p[21]; // 21 is odd: p[21] = c[21]
wire gt = (~S_in[21] & M[21]) | (~(S_in[21] ^ M[21]) & c21);
wire load = en & (first | (gt));

always @(posedge clk) begin
    if (load) M <= S_in;
end

endmodule
