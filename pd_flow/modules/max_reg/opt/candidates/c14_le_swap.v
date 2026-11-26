/*
Jinyuan Zhao
Max comparator
Phase 2 candidate c14: ge written as M <= S_in
*/

module max_reg (
    input  wire              clk,
    input  wire              first,   // first score of the query: take it unconditionally
    input  wire              en,      // a finished score is on S_in this tick
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);

wire load = en && (first || M <= S_in);

always @(posedge clk) begin
    if (load) M <= S_in;
end

endmodule
