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
            assign s[i]     = a[i] ^ (b[i] ^ c[i]);
            assign c[i + 1] = (b[i] & a[i]) | (c[i] & (b[i] ^ a[i]));
        end
    endgenerate
endmodule
