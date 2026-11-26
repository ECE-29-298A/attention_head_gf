/*
Jinyuan Zhao
Max comparator
Phase 2 candidate c13: MSB-first tree comparator (gt/eq pairs), tie don't-care at the leaves
*/

module max_reg (
    input  wire              clk,
    input  wire              first,   // first score of the query: take it unconditionally
    input  wire              en,      // a finished score is on S_in this tick
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);

// Offset binary so the whole compare is unsigned.
wire [21:0] a = {~S_in[21], S_in[20:0]};
wire [21:0] b = {~M[21], M[20:0]};
// Level 0: per-bit greater and equal.
wire [21:0] g0 = a & ~b;
wire [21:0] e0 = ~(a ^ b);
// Pairwise merge: (gh, eh) high, (gl, el) low -> (gh | eh & gl, eh & el).
wire [10:0] g1, e1;
genvar i;
generate for (i = 0; i < 11; i = i + 1) begin : g_l1
    assign g1[i] = g0[2*i+1] | (e0[2*i+1] & g0[2*i]);
    assign e1[i] = e0[2*i+1] & e0[2*i];
end endgenerate
wire [5:0] g2, e2;
generate for (i = 0; i < 5; i = i + 1) begin : g_l2
    assign g2[i] = g1[2*i+1] | (e1[2*i+1] & g1[2*i]);
    assign e2[i] = e1[2*i+1] & e1[2*i];
end endgenerate
assign g2[5] = g1[10]; assign e2[5] = e1[10];
wire [2:0] g3, e3;
generate for (i = 0; i < 3; i = i + 1) begin : g_l3
    assign g3[i] = g2[2*i+1] | (e2[2*i+1] & g2[2*i]);
    assign e3[i] = e2[2*i+1] & e2[2*i];
end endgenerate
wire g4 = g3[1] | (e3[1] & g3[0]);
wire e4 = e3[1] & e3[0];
wire gt = g3[2] | (e3[2] & g4);
wire _unused = &{e4, 1'b0};
wire load = en && (first || gt);

always @(posedge clk) begin
    if (load) M <= S_in;
end

endmodule
