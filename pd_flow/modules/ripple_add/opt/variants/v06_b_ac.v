// ripple_add: s = (a + b + cin) mod 2^N. Technology-independent RTL (Phase 2 candidate).
// Behavioural: one N-bit sum; Yosys alumacc folds the two adds into one $alu/$macc.
// cin is zero-extended explicitly so every operand is N bits wide (lint-clean for N >= 1).
module ripple_add #(parameter N = 16) (
    input  wire [N-1:0] a,
    input  wire [N-1:0] b,
    input  wire         cin,
    output wire [N-1:0] s
);
    wire [N-1:0] ci;
    assign ci[0] = cin;
    generate
        if (N > 1) begin : g_ext
            assign ci[N-1:1] = {(N-1){1'b0}};
        end
    endgenerate
    assign s = b + (a + ci);
endmodule
