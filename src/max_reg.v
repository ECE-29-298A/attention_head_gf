/*
Jinyuan Zhao
Max comparator

Every time a score finishes, keep the larger of it and the maximum so far.
No reset or clear: `first` takes the query's first score unconditionally.
*/

module max_reg (
    input  wire              clk,
    input  wire              first,   // first score of this query
    input  wire              en,      // a finished score is on S_in this tick
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);

always @(posedge clk)
    if (en && (first || S_in > M)) M <= S_in;

endmodule
