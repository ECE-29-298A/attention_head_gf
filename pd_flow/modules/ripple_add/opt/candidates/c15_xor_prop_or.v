// ripple_add: s = (a + b + cin) mod 2^N. Technology-independent RTL (Phase 2 candidate).
// Propagate p = a^b shared: c' = (a&b) | (p&c) written with p, sum p^c (golden form, p explicit).
module ripple_add #(parameter N = 16) (
    input  wire [N-1:0] a,
    input  wire [N-1:0] b,
    input  wire         cin,
    output wire [N-1:0] s
);
    wire [N-1:0] p = a ^ b;
    wire [N-1:0] c;
    assign c[0] = cin;
    genvar i;
    generate
        for (i = 0; i < N - 1; i = i + 1) begin : fa
            assign c[i + 1] = (a[i] & b[i]) | (p[i] & c[i]);
        end
    endgenerate
    assign s = p ^ c;
endmodule
