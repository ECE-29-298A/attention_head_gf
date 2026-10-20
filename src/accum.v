/*
Jinyuan Zhao
L and O0 to O3
*/

/*
Here we add everything up for the average.
Keep 5 running totals:
- L:    sum of all weights
- O0:   sum of W x value 0
- O1:   sum of W x value 1
- O2:   sum of W x value 2
- O3:   sum of W x value 3

After this the divider will do O/L to get weighted average. 
*/

/*
==== INFO ====
THIS USES UP 4 MULTIPLIERS AT ONCE
WE CAN TECHNICALLY USE THE SHARED MAC FOR THIS COMPUTATION (NEED CONTROL LOGIC)
*/

module accum (
    input  wire              clk,
    input  wire              rst_n,
    input  wire              clear,   // pass 2 starting
    input  wire              en,      // a weight and its 4 values are ready
    input  wire        [7:0] W,       // 0 to 255, UNSIGNED
    input  wire signed [3:0] v0, v1, v2, v3,
    output reg        [11:0] L,
    output reg signed [15:0] O0, O1, O2, O3
);

/*
L = L + W
O0 = O0 + W × v0
O1 = O1 + W × v1
O2 = O2 + W × v2
O3 = O3 + W × v3
*/

always@(posedge clk) begin

    if (!rst_n) begin
        L <= 0;
        O0 <= 0;
        O1 <= 0;
        O2 <= 0;
        O3 <= 0;
    end else if (clear) begin
        L <= 0;
        O0 <= 0;
        O1 <= 0;
        O2 <= 0;
        O3 <= 0;
    end else if (en) begin
        L <= L + W;
        O0 <= O0 + $signed({1'b0, W}) * v0;
        O1 <= O1 + $signed({1'b0, W}) * v1;
        O2 <= O2 + $signed({1'b0, W}) * v2;
        O3 <= O3 + $signed({1'b0, W}) * v3;
    end

end

endmodule