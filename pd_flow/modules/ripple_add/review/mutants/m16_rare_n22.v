// MUTANT m16_rare_n22: only at N=22 for the single input a=KA[21:0], b=KB[21:0], cin=1: s[0] flipped (1 of 2^45 inputs)
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
    localparam [63:0] KA = 64'h9E3779B97F4A7C15, KB = 64'hD1B54A32D192ED03;
    localparam [63:0] KC = 64'h0000000000000ABC, KD = 64'h00000000000009F0;
    wire [N:0] c;
    assign c[0] = cin;
    genvar i;
    generate
        for (i = 0; i < N; i = i + 1) begin : fa
            assign s[i]     = a[i] ^ b[i] ^ c[i] ^ (N == 22 && i == 0 && a == KA[N-1:0] && b == KB[N-1:0] && cin);
            assign c[i + 1] = (a[i] & b[i]) | (c[i] & (a[i] ^ b[i]));
        end
    endgenerate
endmodule
