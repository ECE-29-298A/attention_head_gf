// ripple_add: s = (a + b + cin) mod 2^N. Technology-independent RTL (Phase 2 candidate).
// Behavioural form with cin folded into one (N+1)-bit add: {a,1}+{b,cin}, drop bit 0.
module ripple_add #(parameter N = 16) (
    input  wire [N-1:0] a,
    input  wire [N-1:0] b,
    input  wire         cin,
    output wire [N-1:0] s
);
    wire [N:0] t = {a, 1'b1} + {b, cin};
    assign s = t[N:1];
endmodule
