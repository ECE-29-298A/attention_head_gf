// Agent 2 independent miter: golden ripple_add (renamed ripple_add_golden) vs DUT ripple_add.
// All inputs free, no assumptions. Also an independent behavioural reference check.
module miter #(parameter N = 22) (input wire [N-1:0] a, b, input wire cin);
    wire [N-1:0] s_gold, s_dut;
    ripple_add_golden #(.N(N)) g (.a(a), .b(b), .cin(cin), .s(s_gold));
    ripple_add        #(.N(N)) d (.a(a), .b(b), .cin(cin), .s(s_dut));
    always @* begin
        eq_gold: assert (s_dut === s_gold);
    end
endmodule
