// mutant m14_rare_pair: fault for one rare pair only: S_in = 0x0A5C3E vs M = 0x0A5C3D (adjacent, both positive) does not load
module max_reg (
    input  wire              clk,
    input  wire              first,
    input  wire              en,
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);
wire bad = (S_in == 22'h0A5C3E) && (M == 22'h0A5C3D);
always @(posedge clk) if (en && (first || (S_in > M && !bad))) M <= S_in;
endmodule
