/*
Jinyuan Zhao
Max comparator
Phase 2 candidate c04: 23-bit subtract S_in - M, load on non-negative sign (ge)
*/

module max_reg (
    input  wire              clk,
    input  wire              first,   // first score of the query: take it unconditionally
    input  wire              en,      // a finished score is on S_in this tick
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);

wire signed [22:0] d = {S_in[21], S_in} - {M[21], M};
wire load = en && (first || !d[22]);
wire _unused = &{d[21:0], 1'b0};

always @(posedge clk) begin
    if (load) M <= S_in;
end

endmodule
