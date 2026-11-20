/*
Jinyuan Zhao
dot64 function

NO MULTIPLIER: shift-add one bit of ki per cycle through a ripple adder.
qi x ki = qi*k[0] + 2qi*k[1] + ... + 64qi*k[6] - 128qi*k[7]  (ki is two's complement).
Caller holds en for 8 cycles per component (bit_sel = 0..7), 64 components per
score. No reset or clear: `first` (only together with en) adds to 0 instead of S.
While en is low the adder adds 0, so S holds without a hold mux.
*/

module score_mac (
    input wire clk,
    input wire first, // first bit of a new score
    input wire en,

    input wire signed [7:0] qi,
    input wire signed [7:0] ki,
    input wire        [2:0] bit_sel, // which bit of ki this cycle adds
    output reg signed [21:0] S,      // |S| <= 64 * 128 * 128 = 1048576
    output wire signed [21:0] S_next // the value S takes on the next edge
);

wire [21:0] term = en && ki[bit_sel] ? ({{14{qi[7]}}, qi} << bit_sel) : 22'd0;
// Sign bit of ki has weight -128: subtract via ~term + 1. With en low term is 0
// and ~0 + 1 adds 0 as well, so neg needs no en.
wire        neg  = bit_sel == 3'd7;
ripple_add #(.N(22)) s_adder (.a(first ? 22'd0 : S), .b(neg ? ~term : term), .cin(neg), .s(S_next));

always @(posedge clk) S <= S_next;

endmodule

