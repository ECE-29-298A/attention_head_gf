module shf_or #(parameter REGISTERED=0)(input [21:0] D, input [3:0] shift, output [5:0] aligned, output ovf);
wire [20:0] dg = {D[19:0], 1'b0};
wire [12:0] w8 = {dg[20:13] | ({8{!shift[3]}} & dg[12:5]),
                  shift[3] ? dg[12:8] : dg[4:0]};
wire [8:0] w4 = {w8[12:9] | ({4{!shift[2]}} & w8[8:5]),
                 shift[2] ? w8[8:4] : w8[4:0]};
wire [6:0] w2 = {w4[8:7] | ({2{!shift[1]}} & w4[6:5]),
                 shift[1] ? w4[6:2] : w4[4:0]};
wire [5:0] win = {w2[6] | (!shift[0] & w2[5]),
                  shift[0] ? w2[5:1] : w2[4:0]};
wire win_ovf = (|D[21:20]) ||
    (!shift[3] && (|dg[20:13])) ||
    (!shift[2] && (|w8[12:9])) ||
    (!shift[1] && (|w4[8:7])) ||
    (!shift[0] && w2[6]);
assign aligned=win; assign ovf=win_ovf;
endmodule
