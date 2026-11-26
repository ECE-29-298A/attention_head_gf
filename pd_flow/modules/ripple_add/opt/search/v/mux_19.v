// ripple_add search variant mux_19: s = (a + b + cin) mod 2^N
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
                assign s[i] = (b[i] ^ a[i] ^ k[i]);
                if (i < N - 1) begin : g_c
                    assign k[i + 1] = ((a[i] ^ b[i]) ? k[i] : b[i]);
                end
            end else begin : g_o
                assign s[i] = (k[i] ^ b[i] ^ a[i]);
                if (i < N - 1) begin : g_c
                    assign k[i + 1] = ((a[i] ^ b[i]) ? k[i] : b[i]);
                end
            end
        end
    endgenerate
endmodule
