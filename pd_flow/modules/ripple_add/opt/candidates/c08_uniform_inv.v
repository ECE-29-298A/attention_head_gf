// ripple_add: s = (a + b + cin) mod 2^N. Technology-independent RTL (Phase 2 candidate).
// Uniform inverted carry kn = ~c: kn' = ~((a|b) & ~(~(a&b) & kn)), s = ~(a^b^kn).
module ripple_add #(parameter N = 16) (
    input  wire [N-1:0] a,
    input  wire [N-1:0] b,
    input  wire         cin,
    output wire [N-1:0] s
);
    wire [N-1:0] kn;
    assign kn[0] = ~cin;
    genvar i;
    generate
        for (i = 0; i < N; i = i + 1) begin : fa
            assign s[i] = ~(a[i] ^ b[i] ^ kn[i]);
            if (i < N - 1) begin : g_c
                assign kn[i + 1] = ~((a[i] | b[i]) & ~(~(a[i] & b[i]) & kn[i]));
            end
        end
    endgenerate
endmodule
