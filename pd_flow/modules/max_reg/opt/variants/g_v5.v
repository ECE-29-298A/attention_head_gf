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
*/

wire load = (en && first) || (en && S_in > M);

always @(posedge clk) begin
    if (load) M <= S_in;
end

endmodule
