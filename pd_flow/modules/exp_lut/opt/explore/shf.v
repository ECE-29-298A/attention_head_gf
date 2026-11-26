module shf #(parameter REGISTERED=0)(input [21:0] D, input [3:0] shift, output [5:0] aligned, output ovf);
wire [20:0] delta_guard = {D[19:0], 1'b0};
wire [12:0] stage8 = shift[3] ? delta_guard[20:8] : delta_guard[12:0];
wire [8:0] stage4 = shift[2] ? stage8[12:4] : stage8[8:0];
wire [6:0] stage2 = shift[1] ? stage4[8:2] : stage4[6:0];
assign aligned = shift[0] ? stage2[6:1] : stage2[5:0];
assign ovf = (|D[21:20]) || (!shift[3] && (|delta_guard[20:13])) || (!shift[2] && (|stage8[12:9])) || (!shift[1] && (|stage4[8:7])) || (!shift[0] && stage2[6]);
endmodule
