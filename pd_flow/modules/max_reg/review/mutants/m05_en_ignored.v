// mutant m05_en_ignored: en ignored
module max_reg (
    input  wire              clk,
    input  wire              first,
    input  wire              en,
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);
always @(posedge clk) if (first || S_in > M) M <= S_in;
endmodule
