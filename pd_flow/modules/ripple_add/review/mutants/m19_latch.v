// MUTANT m19_latch: output through an always @* latch that holds when a==b==all ones (else transparent)
// Derived from the golden ripple_add.v.
/*
Shared by accum and score_mac.
*/

// Hand-written ripple-carry adder: N full adders chained, carry out dropped (wraps like +).
module ripple_add #(parameter N = 16) (
    input  wire [N-1:0] a,
    input  wire [N-1:0] b,
    input  wire         cin,
    output reg  [N-1:0] s
);
    wire [N-1:0] s_g;
    always @* if (!(a == {N{1'b1}} && b == {N{1'b1}})) s = s_g;
    wire [N:0] c;
    assign c[0] = cin;
    genvar i;
    generate
        for (i = 0; i < N; i = i + 1) begin : fa
            assign s_g[i]   = a[i] ^ b[i] ^ c[i];
            assign c[i + 1] = (a[i] & b[i]) | (c[i] & (a[i] ^ b[i]));
        end
    endgenerate
endmodule
