// ripple_add: s = (a + b + cin) mod 2^N. Technology-independent RTL (Phase 2 candidate).
// Behavioural subtract form: a - ~b - (1 - cin) == a + b + cin (mod 2^N).
module ripple_add #(parameter N = 16) (
    input  wire [N-1:0] a,
    input  wire [N-1:0] b,
    input  wire         cin,
    output wire [N-1:0] s
);
    wire [N-1:0] cn;
    assign cn[0] = ~cin;
    generate
        if (N > 1) begin : g_ext
            assign cn[N-1:1] = {(N-1){1'b0}};
        end
    endgenerate
    assign s = a - ~b - cn;
endmodule
