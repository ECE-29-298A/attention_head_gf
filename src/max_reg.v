/*
Jinyuan Zhao
Max comparator
*/

module max_reg (
    input  wire              clk,
    input  wire              rst_n,
    input  wire              clear,   // new query starting, forget the old max
    input  wire              en,      // a finished score is on S_in this tick
    input  wire signed [9:0] S_in,
    output reg  signed [9:0] M
);

/*
Every time we finished a score (from score_mac), max_reg compares to the biggest one it's seen so far and keep whichever one is larger.
After the last key it will hold M (top score)
*/

always@(posedge clk) begin

    if (!rst_n) begin
        M <= -224; // CHANGE THIS IF WE GO TO INT8 (Very likely!)
    end else if (clear) begin
        M <= -224;
    end else if (en) begin
        if (S_in > M) begin
            M <= S_in;
        end
    end

end


endmodule
