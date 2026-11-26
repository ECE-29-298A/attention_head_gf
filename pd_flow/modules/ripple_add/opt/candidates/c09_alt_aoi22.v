// ripple_add: s = (a + b + cin) mod 2^N. Technology-independent RTL (Phase 2 candidate).
// Alternating polarity: even stage kn=~(ab|c(a|b)); odd stage c=~(~(ab)&(~(a|b)|kn)).
module ripple_add #(parameter N = 16) (
    input  wire [N-1:0] a,
    input  wire [N-1:0] b,
    input  wire         cin,
    output wire [N-1:0] s
);
    wire [N-1:0] k; // k[i] = c[i] (i even), ~c[i] (i odd)
    assign k[0] = cin;
    genvar i;
    generate
        for (i = 0; i < N; i = i + 1) begin : fa
            if (i % 2 == 0) begin : g_even
                assign s[i] = a[i] ^ b[i] ^ k[i];
                if (i < N - 1) begin : g_c
                    assign k[i + 1] = ~((a[i] & b[i]) | (k[i] & (a[i] | b[i])));
                end
            end else begin : g_odd
                assign s[i] = ~(a[i] ^ b[i] ^ k[i]);
                if (i < N - 1) begin : g_c
                    assign k[i + 1] = ~(~(a[i] & b[i]) & (~(a[i] | b[i]) | k[i]));
                end
            end
        end
    endgenerate
endmodule
