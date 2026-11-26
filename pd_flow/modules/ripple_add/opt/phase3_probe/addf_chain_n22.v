// Phase 3 probe only (NOT a Phase 2 candidate): N=22 chain of GF180 addf_1, for STA/area reference.
module ripple_add (input wire [21:0] a, input wire [21:0] b, input wire cin, output wire [21:0] s);
  wire [22:0] c;
  assign c[0] = cin;
  gf180mcu_fd_sc_mcu7t5v0__addf_1 fa0 (.A(a[0]), .B(b[0]), .CI(c[0]), .S(s[0]), .CO(c[1]));
  gf180mcu_fd_sc_mcu7t5v0__addf_1 fa1 (.A(a[1]), .B(b[1]), .CI(c[1]), .S(s[1]), .CO(c[2]));
  gf180mcu_fd_sc_mcu7t5v0__addf_1 fa2 (.A(a[2]), .B(b[2]), .CI(c[2]), .S(s[2]), .CO(c[3]));
  gf180mcu_fd_sc_mcu7t5v0__addf_1 fa3 (.A(a[3]), .B(b[3]), .CI(c[3]), .S(s[3]), .CO(c[4]));
  gf180mcu_fd_sc_mcu7t5v0__addf_1 fa4 (.A(a[4]), .B(b[4]), .CI(c[4]), .S(s[4]), .CO(c[5]));
  gf180mcu_fd_sc_mcu7t5v0__addf_1 fa5 (.A(a[5]), .B(b[5]), .CI(c[5]), .S(s[5]), .CO(c[6]));
  gf180mcu_fd_sc_mcu7t5v0__addf_1 fa6 (.A(a[6]), .B(b[6]), .CI(c[6]), .S(s[6]), .CO(c[7]));
  gf180mcu_fd_sc_mcu7t5v0__addf_1 fa7 (.A(a[7]), .B(b[7]), .CI(c[7]), .S(s[7]), .CO(c[8]));
  gf180mcu_fd_sc_mcu7t5v0__addf_1 fa8 (.A(a[8]), .B(b[8]), .CI(c[8]), .S(s[8]), .CO(c[9]));
  gf180mcu_fd_sc_mcu7t5v0__addf_1 fa9 (.A(a[9]), .B(b[9]), .CI(c[9]), .S(s[9]), .CO(c[10]));
  gf180mcu_fd_sc_mcu7t5v0__addf_1 fa10 (.A(a[10]), .B(b[10]), .CI(c[10]), .S(s[10]), .CO(c[11]));
  gf180mcu_fd_sc_mcu7t5v0__addf_1 fa11 (.A(a[11]), .B(b[11]), .CI(c[11]), .S(s[11]), .CO(c[12]));
  gf180mcu_fd_sc_mcu7t5v0__addf_1 fa12 (.A(a[12]), .B(b[12]), .CI(c[12]), .S(s[12]), .CO(c[13]));
  gf180mcu_fd_sc_mcu7t5v0__addf_1 fa13 (.A(a[13]), .B(b[13]), .CI(c[13]), .S(s[13]), .CO(c[14]));
  gf180mcu_fd_sc_mcu7t5v0__addf_1 fa14 (.A(a[14]), .B(b[14]), .CI(c[14]), .S(s[14]), .CO(c[15]));
  gf180mcu_fd_sc_mcu7t5v0__addf_1 fa15 (.A(a[15]), .B(b[15]), .CI(c[15]), .S(s[15]), .CO(c[16]));
  gf180mcu_fd_sc_mcu7t5v0__addf_1 fa16 (.A(a[16]), .B(b[16]), .CI(c[16]), .S(s[16]), .CO(c[17]));
  gf180mcu_fd_sc_mcu7t5v0__addf_1 fa17 (.A(a[17]), .B(b[17]), .CI(c[17]), .S(s[17]), .CO(c[18]));
  gf180mcu_fd_sc_mcu7t5v0__addf_1 fa18 (.A(a[18]), .B(b[18]), .CI(c[18]), .S(s[18]), .CO(c[19]));
  gf180mcu_fd_sc_mcu7t5v0__addf_1 fa19 (.A(a[19]), .B(b[19]), .CI(c[19]), .S(s[19]), .CO(c[20]));
  gf180mcu_fd_sc_mcu7t5v0__addf_1 fa20 (.A(a[20]), .B(b[20]), .CI(c[20]), .S(s[20]), .CO(c[21]));
  gf180mcu_fd_sc_mcu7t5v0__addf_1 fa21 (.A(a[21]), .B(b[21]), .CI(c[21]), .S(s[21]), .CO(c[22]));
endmodule
