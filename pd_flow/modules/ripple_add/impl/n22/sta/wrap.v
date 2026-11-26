module wrap (input [21:0] a, input [21:0] b, input cin, output [21:0] s);
  ripple_add u (.a(a), .b(b), .cin(cin), .s(s));
endmodule
