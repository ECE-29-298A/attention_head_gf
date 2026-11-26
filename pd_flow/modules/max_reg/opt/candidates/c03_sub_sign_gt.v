/*
Jinyuan Zhao
Max comparator
Phase 2 candidate c03: 23-bit subtract M - S_in, load on negative sign (strict gt)
*/

module max_reg (
    input  wire              clk,
    input  wire              first,   // first score of the query: take it unconditionally
    input  wire              en,      // a finished score is on S_in this tick
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);

wire signed [22:0] d = {M[21], M} - {S_in[21], S_in};
wire load = en && (first || d[22]);
wire _unused = &{d[21:0], 1'b0};

always @(posedge clk) begin
    if (load) M <= S_in;
end

endmodule
