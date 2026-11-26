// MUTANT m14_n22_only_cin1: only at N=22 and cin=1: carry into bit 21 suppressed (breaks mac_unit subtract MSB)
// Derived from the golden ripple_add.v.
/*
Shared by accum and score_mac.
*/

// Hand-written ripple-carry adder: N full adders chained, carry out dropped (wraps like +).
module ripple_add #(parameter N = 16) (
    input  wire [N-1:0] a,
    input  wire [N-1:0] b,
    input  wire         cin,
    output wire [N-1:0] s
);
    wire [N:0] c;
    assign c[0] = cin;
    genvar i;
    generate
        for (i = 0; i < N; i = i + 1) begin : fa
            assign s[i]     = (N == 22 && i == N - 1) ? (a[i] ^ b[i] ^ (c[i] & ~cin)) : (a[i] ^ b[i] ^ c[i]);
            assign c[i + 1] = (a[i] & b[i]) | (c[i] & (a[i] ^ b[i]));
        end
    endgenerate
endmodule
