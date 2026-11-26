// mutant m11_initval: power-up initial value M = 0 (no port change)
module max_reg (
    input  wire              clk,
    input  wire              first,
    input  wire              en,
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);
initial M = 22'd0;
always @(posedge clk) if (en && (first || S_in > M)) M <= S_in;
endmodule
