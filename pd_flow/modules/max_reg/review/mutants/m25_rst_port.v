// mutant m25_rst_port: added synchronous active-low reset port (interface change; power-up behaviour defined)
module max_reg (
    input  wire              clk,
    input  wire              rst_n,
    input  wire              first,
    input  wire              en,
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);
always @(posedge clk) if (!rst_n) M <= 22'd0; else if (en && (first || S_in > M)) M <= S_in;
endmodule
