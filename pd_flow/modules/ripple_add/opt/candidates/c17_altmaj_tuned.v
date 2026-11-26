// ripple_add: s = (a + b + cin) mod 2^N. Technology-independent RTL (Phase 2 candidate).
// Alternating-polarity majority carry (odd stages hold ~c); operand order is the one ABC
// mapped smallest in the operand-order search (search/, variant alt_maj_5).
module ripple_add #(parameter N = 16) (
    input  wire [N-1:0] a,
    input  wire [N-1:0] b,
    input  wire         cin,
    output wire [N-1:0] s
);
    wire [N-1:0] k;
    assign k[0] = cin;
    genvar i;
    generate
        for (i = 0; i < N; i = i + 1) begin : fa
            if (i % 2 == 0) begin : g_e
                assign s[i] = (a[i] ^ k[i] ^ b[i]);
                if (i < N - 1) begin : g_c
                    assign k[i + 1] = ~((a[i] & b[i]) | (a[i] & k[i]) | (k[i] & b[i]));
                end
            end else begin : g_o
                assign s[i] = ~(b[i] ^ a[i] ^ k[i]);
                if (i < N - 1) begin : g_c
                    assign k[i + 1] = ~((~b[i] & k[i]) | (~a[i] & ~b[i]) | (k[i] & ~a[i]));
                end
            end
        end
    endgenerate
endmodule
