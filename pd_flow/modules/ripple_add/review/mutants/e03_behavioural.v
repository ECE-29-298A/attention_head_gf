// MUTANT e03_behavioural: behavioural adder, functionally equivalent
module ripple_add #(parameter N = 16) (
    input  wire [N-1:0] a,
    input  wire [N-1:0] b,
    input  wire         cin,
    output wire [N-1:0] s
);
    assign s = a + b + {{(N-1){1'b0}}, cin};
endmodule
