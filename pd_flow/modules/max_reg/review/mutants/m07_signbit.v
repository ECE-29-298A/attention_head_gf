// mutant m07_signbit: sign-bit fault: sign-differing pairs decided inverted (positive S vs negative M holds, negative S vs positive M loads)
module max_reg (
    input  wire              clk,
    input  wire              first,
    input  wire              en,
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);
wire gt = (S_in[21] != M[21]) ? S_in[21] : (S_in[20:0] > M[20:0]);
always @(posedge clk) if (en && (first || gt)) M <= S_in;
endmodule
