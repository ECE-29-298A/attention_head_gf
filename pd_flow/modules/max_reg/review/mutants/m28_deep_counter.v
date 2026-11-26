// mutant m28_deep_counter: deep-state bug: after 1000 consecutive en = 0 cycles, M bit 3 flips once (hidden 10-bit counter)
module max_reg (
    input  wire              clk,
    input  wire              first,
    input  wire              en,
    input  wire signed [21:0] S_in,
    output reg  signed [21:0] M
);
reg [9:0] idle;
always @(posedge clk) begin
    idle <= en ? 10'd0 : (idle == 10'd1000 ? 10'd0 : idle + 10'd1);
    if (en && (first || S_in > M)) M <= S_in;
    else if (idle == 10'd1000) M <= M ^ 22'd8;
end
endmodule
