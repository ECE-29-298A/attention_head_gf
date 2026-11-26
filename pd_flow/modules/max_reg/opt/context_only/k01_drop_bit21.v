/*
Context-only exploration k01 (NOT standalone-compliant, area probe only, never proven):
in the controller, every value M takes after a load is a pass-1 score in
[-1,040,384, 2^20], where M[21] == M[20] & |M[19:0]. Store 21 flops and rebuild M[21].
*/
module max_reg (
    input  wire              clk,
    input  wire              first,
    input  wire              en,
    input  wire signed [21:0] S_in,
    output wire signed [21:0] M
);
reg [20:0] m;
assign M = {m[20] & |m[19:0], m};
always @(posedge clk) begin
    if (en && (first || S_in > M)) m <= S_in[20:0];
end
endmodule
