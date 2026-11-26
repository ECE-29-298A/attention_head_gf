// mutant m15_minneg: fault only when M is the most-negative value: nothing beats MINNEG
module max_reg (
    input  wire              clk,
    input  wire              first,
    input  wire              en,
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);
wire bad = (M == 22'h200000);
always @(posedge clk) if (en && (first || (S_in > M && !bad))) M <= S_in;
endmodule
