/*
Jinyuan Zhao
Max comparator
Phase 2 candidate c07: carry out of offset-binary S + ~M (no +1: strict gt)
*/

module max_reg (
    input  wire              clk,
    input  wire              first,   // first score of the query: take it unconditionally
    input  wire              en,      // a finished score is on S_in this tick
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);

wire [21:0] s_ob = {~S_in[21], S_in[20:0]};
wire [21:0] m_ob = {~M[21], M[20:0]};
wire [22:0] t = {1'b0, s_ob} + {1'b0, ~m_ob};
wire load = en && (first || t[22]);
wire _unused = &{t[21:0], 1'b0};

always @(posedge clk) begin
    if (load) M <= S_in;
end

endmodule
