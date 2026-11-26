/*
Jinyuan Zhao
Max comparator
Phase 2 candidate c06: offset-binary unsigned compare (MSB inverted), ge
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
wire load = en && (first || s_ob >= m_ob);

always @(posedge clk) begin
    if (load) M <= S_in;
end

endmodule
