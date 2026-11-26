module wrap (input [11:0] a, input [11:0] b, input cin, output [11:0] s);
  ripple_add u (.a(a), .b(b), .cin(cin), .s(s));
endmodule
