module ripple_add (input wire [11:0] a, input wire [11:0] b, input wire cin, output wire [11:0] s);
  wire [12:0] c;
  assign c[0] = cin;
  gf180mcu_fd_sc_mcu7t5v0__addf_2 u_fa0 (.A(a[0]), .B(b[0]), .CI(c[0]), .S(s[0]), .CO(c[1]));
  gf180mcu_fd_sc_mcu7t5v0__addf_2 u_fa1 (.A(a[1]), .B(b[1]), .CI(c[1]), .S(s[1]), .CO(c[2]));
  gf180mcu_fd_sc_mcu7t5v0__addf_2 u_fa2 (.A(a[2]), .B(b[2]), .CI(c[2]), .S(s[2]), .CO(c[3]));
  gf180mcu_fd_sc_mcu7t5v0__addf_2 u_fa3 (.A(a[3]), .B(b[3]), .CI(c[3]), .S(s[3]), .CO(c[4]));
  gf180mcu_fd_sc_mcu7t5v0__addf_2 u_fa4 (.A(a[4]), .B(b[4]), .CI(c[4]), .S(s[4]), .CO(c[5]));
  gf180mcu_fd_sc_mcu7t5v0__addf_2 u_fa5 (.A(a[5]), .B(b[5]), .CI(c[5]), .S(s[5]), .CO(c[6]));
  gf180mcu_fd_sc_mcu7t5v0__addf_2 u_fa6 (.A(a[6]), .B(b[6]), .CI(c[6]), .S(s[6]), .CO(c[7]));
  gf180mcu_fd_sc_mcu7t5v0__addf_2 u_fa7 (.A(a[7]), .B(b[7]), .CI(c[7]), .S(s[7]), .CO(c[8]));
  gf180mcu_fd_sc_mcu7t5v0__addf_2 u_fa8 (.A(a[8]), .B(b[8]), .CI(c[8]), .S(s[8]), .CO(c[9]));
  gf180mcu_fd_sc_mcu7t5v0__addf_2 u_fa9 (.A(a[9]), .B(b[9]), .CI(c[9]), .S(s[9]), .CO(c[10]));
  gf180mcu_fd_sc_mcu7t5v0__addf_2 u_fa10 (.A(a[10]), .B(b[10]), .CI(c[10]), .S(s[10]), .CO(c[11]));
  gf180mcu_fd_sc_mcu7t5v0__xor3_1 u_msb (.A1(a[11]), .A2(b[11]), .A3(c[11]), .Z(s[11]));
  assign c[12] = 1'b0;
endmodule
