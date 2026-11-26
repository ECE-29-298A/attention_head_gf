// ripple_add: s = (a + b + cin) mod 2^N. Technology-independent RTL (Phase 2 candidate).
// Alternating-polarity ripple: odd stages carry the complement of the carry, so each
// stage is a single inverting majority (maj(~x,~y,~z) = ~maj(x,y,z)).
module ripple_add #(parameter N = 16) (
    input  wire [N-1:0] a,
    input  wire [N-1:0] b,
    input  wire         cin,
    output wire [N-1:0] s
);
    // k[i] = c[i] for even i, ~c[i] for odd i
    wire [N-1:0] k;
    assign k[0] = cin;
    genvar i;
    generate
        for (i = 0; i < N; i = i + 1) begin : fa
            if (i % 2 == 0) begin : g_even
                // inputs true polarity: s = a^b^c ; next (odd) = ~maj(a,b,c)
                assign s[i] = a[i] ^ b[i] ^ k[i];
                if (i < N - 1) begin : g_c
                    assign k[i + 1] = ~((a[i] & b[i]) | (a[i] & k[i]) | (b[i] & k[i]));
                end
            end else begin : g_odd
                // k = ~c: s = ~(a^b^k); next (even) c' = maj(a,b,c) = ~maj(~a,~b,k)
                assign s[i] = ~(a[i] ^ b[i] ^ k[i]);
                if (i < N - 1) begin : g_c
                    assign k[i + 1] = ~((~a[i] & ~b[i]) | (~a[i] & k[i]) | (~b[i] & k[i]));
                end
            end
        end
    endgenerate
endmodule
