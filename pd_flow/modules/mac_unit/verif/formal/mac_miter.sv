// seq_eq item (SPEC.md section 5): sequential equivalence miter of the golden (module
// mac_gold, the snapshot renamed by run_all.sh) against the candidate (module mac_unit), both
// driven by the same free inputs.
//
// Anchor (mac_unit has no reset): FLUSH ANCHORING. Both instances start in arbitrary,
// independent power-up states (no initial value on either; guarded in seq_eq.sby). Harness
// observers track, from the inputs alone, which golden outputs have become functions of the
// inputs only ("fresh"), following the equations of SPEC R1-R10:
//   fresh_s       S was loaded (R3), or last written by score_en in accum_mode from a fresh
//                 head or a first-token load (R4);
//   fresh_l       L was written with first = 1 since power-up (R10);
//   fresh_ring[j] ring slot j (j = 0 is the head O0) was last written from a fresh head or a
//                 first-token load (R6-R8); the vector rotates with the ring every clock.
// a_eq compares each output whenever it is fresh. A correct candidate (port-equivalent to the
// golden from corresponding start states) must therefore pass for ANY pair of start states,
// and this is exactly the behaviour the controller consumes: it loads S before every score,
// loads L at token 0 and loads every ring slot at the first token's bit 7 (SPEC 5.1).
// What happens before a flush (the power-up behaviour) is NOT compared here; it is pinned for
// every DUT by the gating black-box items fv_spec_* (SPEC 4) plus the structure checks.
//   - There are NO assumptions (assume, restrict, anyconst, anyseq) anywhere.
//   - Optional candidate-supplied lemmas over gold.*, cand.* and the read-only observers
//     fresh_s / fresh_l / fresh_ring are included from seq_lemmas.vh (formal/lemma_prep.py).
//     They are ASSERTIONS, proven together with a_eq, never assumed.
// -DP_OUTPUTS=2|4|8 -DP_SELW=1|2|3 select the configuration; fv_mode.vh defines GATE for a
// gate-level candidate (no parameter).
`include "fv_mode.vh"
module mac_miter (
    input wire              clk,
    input wire              accum_mode,
    input wire              load, subtract,
    input wire       [21:0] M,
    input wire              score_en,
    input wire        [7:0] qi, ki,
    input wire              first, accum_en,
    input wire        [7:0] W,
    input wire [`P_SELW-1:0] sel,
    input wire        [7:0] v,
    input wire        [2:0] bit_sel
);
    localparam P = `P_OUTPUTS;
    wire [21:0] g_S, c_S;
    wire [11:0] g_L, c_L;
    wire [19:0] g_O0, c_O0;
    mac_gold #(.OUTPUTS(P)) gold (
        .clk(clk), .accum_mode(accum_mode), .load(load), .subtract(subtract), .M(M),
        .score_en(score_en), .qi(qi), .ki(ki), .first(first), .accum_en(accum_en), .W(W),
        .sel(sel), .v(v), .bit_sel(bit_sel), .S(g_S), .L(g_L), .O0(g_O0));
`ifdef GATE
    mac_unit cand (
`else
    mac_unit #(.OUTPUTS(P)) cand (
`endif
        .clk(clk), .accum_mode(accum_mode), .load(load), .subtract(subtract), .M(M),
        .score_en(score_en), .qi(qi), .ki(ki), .first(first), .accum_en(accum_en), .W(W),
        .sel(sel), .v(v), .bit_sel(bit_sel), .S(c_S), .L(c_L), .O0(c_O0));

    // freshness observers: initialised to "nothing determined yet"
    reg         fresh_s = 1'b0;
    reg         fresh_l = 1'b0;
    reg [P-1:0] fresh_ring = {P{1'b0}};
    wire load_o = accum_en && first && bit_sel == 3'd7;          // R6: head replaced by 0
    wire head_f = load_o || fresh_ring[0];                       // accum-mode adder input fresh
    always @(posedge clk) begin
        fresh_ring <= {accum_mode ? head_f : fresh_ring[0], fresh_ring[P-1:1]};
        if (load) fresh_s <= 1'b1;
        else if (score_en && accum_mode) fresh_s <= head_f;
        if (accum_en && sel == 0 && bit_sel == 3'd0) fresh_l <= first || fresh_l;
    end

    always @* begin
`ifdef SANITY_EQ
        a_wrong_eq: assert (!fresh_s || c_S == g_S + 22'd1);    // negative control: must be refuted
`else
        a_eq: assert ((!fresh_s || c_S == g_S) && (!fresh_l || c_L == g_L)
                      && (!fresh_ring[0] || c_O0 == g_O0));
`endif
    end

`include "seq_lemmas.vh"
endmodule
