// ripple_add search variant maj_25: s = (a + b + cin) mod 2^N
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
                assign s[i] = (k[i] ^ a[i] ^ b[i]);
                if (i < N - 1) begin : g_c
                    assign k[i + 1] = ((k[i] & b[i]) | (b[i] & a[i]) | (a[i] & k[i]));
                end
            end else begin : g_o
                assign s[i] = (a[i] ^ k[i] ^ b[i]);
                if (i < N - 1) begin : g_c
                    assign k[i + 1] = ((b[i] & a[i]) | (b[i] & k[i]) | (a[i] & k[i]));
                end
            end
        end
    endgenerate
endmodule
