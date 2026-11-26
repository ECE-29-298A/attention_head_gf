// ripple_add: s = (a + b + cin) mod 2^N. Technology-independent RTL (Phase 2 candidate).
// Ripple with majority-form carry c' = ab | ac | bc.
module ripple_add #(parameter N = 16) (
    input  wire [N-1:0] a,
    input  wire [N-1:0] b,
    input  wire         cin,
    output wire [N-1:0] s
);
    wire [N-1:0] c;
    assign c[0] = cin;
    genvar i;
    generate
        for (i = 0; i < N; i = i + 1) begin : fa
            assign s[i] = a[i] ^ b[i] ^ c[i];
            if (i < N - 1) begin : g_c
                assign c[i + 1] = (a[i] & b[i]) | (a[i] & c[i]) | (b[i] & c[i]);
            end
        end
    endgenerate
endmodule
