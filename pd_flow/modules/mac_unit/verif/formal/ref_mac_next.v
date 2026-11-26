// Independent reference of the mac_unit next-state equations (SPEC.md R1-R12), written from
// the SPEC, not from the RTL: two's-complement bit weights and products, no shared adder,
// no ~x + 1 negation, no shift of a sign-extended operand.
//   current state (S, L, O0 = ring head) + inputs  ->  S_n, L_n, tail_n
// tail_n is the value that enters the ring tail at this edge, i.e. O0 OUTPUTS edges later.
// bit weight of bit b of a two's-complement byte:  w(b) = 2^b for b < 7, w(7) = -128;
// every w(b) fits in a signed 8-bit number.
// MUT (negative controls only, run_all.sh sanity tasks; 0 = the reference):
//   1  bit 7 weighs +128 instead of -128 (score and accumulate)
//   2  L updates whenever accum_en && bit_sel == 0 (the sel == 0 condition dropped)
module ref_mac_next #(parameter MUT = 0) (
    input  wire              accum_mode,
    input  wire              load, subtract,
    input  wire       [21:0] M,
    input  wire              score_en,
    input  wire signed [7:0] qi,
    input  wire        [7:0] ki,
    input  wire              first, accum_en,
    input  wire        [7:0] W,
    input  wire              sel_zero,        // sel == 0
    input  wire        [7:0] v,
    input  wire        [2:0] bit_sel,
    input  wire       [21:0] S,
    input  wire       [11:0] L,
    input  wire signed [19:0] O0,
    output wire       [21:0] S_n,
    output wire       [11:0] L_n,
    output wire       [19:0] tail_n
);
    wire signed [7:0] w = (bit_sel == 3'd7) ? ((MUT == 1) ? 8'sd0 : -8'sd128)
                                            : $signed(8'd1 << bit_sel);
    // MUT 1: +128 does not fit in 8 signed bits; use the 9-bit form below
    wire signed [8:0] w9 = (MUT == 1 && bit_sel == 3'd7) ? 9'sd128 : {w[7], w};
    // R1/R2 score: S + qi * ki_b * w(b), or minus it when subtract (pass 2)
    wire signed [8:0]  kb    = ki[bit_sel] ? w9 : 9'sd0;
    wire signed [17:0] prod  = qi * kb;                                   // |.| <= 2^14
    wire signed [23:0] s_sc  = $signed(S) + (subtract ? -prod : prod);    // wraps to 22 bits
    // R5/R6 accumulate: head (0 at the first token's bit 7) + W * v_b * w(b)
    wire signed [8:0]  vb    = (accum_en && v[bit_sel]) ? w9 : 9'sd0;
    wire signed [18:0] vprod = $signed({1'b0, W}) * vb;                   // |.| <= 2^15
    wire               fresh = accum_en && first && bit_sel == 3'd7;
    wire signed [23:0] h_acc = (fresh ? 24'sd0 : O0) + vprod;            // O0 sign-extended
    assign tail_n = accum_mode ? h_acc[19:0] : O0;                          // R7/R8
    assign S_n = load ? (subtract ? M : 22'd0)                              // R3
               : score_en ? (accum_mode ? h_acc[21:0] : s_sc[21:0])        // R1, R4
               : S;
    wire upd = accum_en && bit_sel == 3'd0 && (sel_zero || MUT == 2);
    wire [12:0] l_sum = (first ? 13'd0 : {1'b0, L}) + {5'd0, W};
    assign L_n = upd ? l_sum[11:0] : L;                                     // R10
endmodule
