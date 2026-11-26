// Black-box formal property harness for mac_unit (SPEC.md section 4). Ports only: no DUT
// internal name is referenced, so the same harness checks the golden RTL, a candidate RTL
// and a gate-level netlist.
//   - No assumptions: every input is free at every step.
//   - The DUT carries no initial value (guarded in mac.sby), so its power-up state (S, L and
//     the whole ring) is arbitrary: every property holds FROM ANY START STATE.
//   - The only initialised registers are this harness's observers (pv, cnt), which start in
//     "nothing observed yet" and never drive the DUT.
// The expected values come from ref_mac_next (independent reference of the equations),
// evaluated on the DUT's CURRENT port values and registered:
//   a_S   S(t+1) == S_n(t)                                     R1-R4, R11
//   a_L   L(t+1) == L_n(t)                                     R10
//   a_O0  O0(t+P) == tail_n(t), P = OUTPUTS                    R5-R9 (ring as seen at O0)
// Groups (one per SBY task, selected by define): SPEC, COVERS, SANITY_SIGN (reference with bit
// 7 weighing +128), SANITY_LSEL (L condition without sel == 0), SANITY_DELAY (O0 checked
// P-1 edges later instead of P). The SANITY_* wrong properties MUST be refuted.
`include "fv_mode.vh"
module mac_props (
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
    localparam P = `P_OUTPUTS;            // -DP_OUTPUTS=2|4|8 -DP_SELW=1|2|3 (mac.sby task)
`ifdef SANITY_SIGN
    localparam MUT = 1;
`elsif SANITY_LSEL
    localparam MUT = 2;
`else
    localparam MUT = 0;
`endif

    wire [21:0] S;
    wire [11:0] L;
    wire [19:0] O0;
`ifdef GATE
    mac_unit dut (
`else
    mac_unit #(.OUTPUTS(P)) dut (
`endif
        .clk(clk), .accum_mode(accum_mode), .load(load), .subtract(subtract), .M(M),
        .score_en(score_en), .qi(qi), .ki(ki), .first(first), .accum_en(accum_en), .W(W),
        .sel(sel), .v(v), .bit_sel(bit_sel), .S(S), .L(L), .O0(O0));

    wire [21:0] S_n;
    wire [11:0] L_n;
    wire [19:0] tail_n;
    ref_mac_next #(.MUT(MUT)) ref0 (
        .accum_mode(accum_mode), .load(load), .subtract(subtract), .M(M), .score_en(score_en),
        .qi(qi), .ki(ki), .first(first), .accum_en(accum_en), .W(W), .sel_zero(sel == 0),
        .v(v), .bit_sel(bit_sel), .S(S), .L(L), .O0(O0), .S_n(S_n), .L_n(L_n), .tail_n(tail_n));

    // observers
    reg        pv = 1'b0;                 // a previous cycle exists
    reg  [3:0] cnt = 4'd0;                // edges seen, saturating at P
    reg [21:0] S_exp;
    reg [11:0] L_exp;
    reg [20*P-1:0] tq;                    // tail values in flight; tq[19:0] is due at O0 now
    // previous-cycle inputs and outputs (covers)
    reg        p_am, p_load, p_sub, p_se, p_first, p_ae, p_top, p_b0, p_sel0, p_vb, p_kb;
    reg [21:0] p_S, p_M;
    reg [11:0] p_L;
    reg [19:0] p_O0;
    reg  [7:0] p_W, p_qi;
    always @(posedge clk) begin
        pv <= 1'b1;
        if (cnt != P) cnt <= cnt + 4'd1;
        S_exp <= S_n;
        L_exp <= L_n;
        tq <= {tail_n, tq[20*P-1:20]};
        p_am <= accum_mode; p_load <= load; p_sub <= subtract; p_se <= score_en;
        p_first <= first; p_ae <= accum_en; p_top <= bit_sel == 3'd7; p_b0 <= bit_sel == 3'd0;
        p_sel0 <= sel == 0; p_vb <= v[bit_sel]; p_kb <= ki[bit_sel];
        p_S <= S; p_M <= M; p_L <= L; p_O0 <= O0; p_W <= W; p_qi <= qi;
    end

    // covers only: a value written at the tail, followed to the head (P edges later)
    reg [3:0]  age = 4'd0;                // 0 = nothing tracked
    reg [19:0] trk;
    reg        trk_lo;                    // tracked value came from a first-token load (R6)
    always @(posedge clk)
        if (age == 0 && accum_mode && accum_en && bit_sel == 3'd7 && v[7] && W == 8'd255) begin
            age <= 4'd1; trk <= tail_n; trk_lo <= first;
        end else if (age != 0 && age != P) age <= age + 4'd1;

    always @* begin
`ifdef SPEC
        a_S:  assert (!pv || S == S_exp);
        a_L:  assert (!pv || L == L_exp);
        a_O0: assert (cnt != P || O0 == tq[19:0]);
`endif
`ifdef SANITY_SIGN
        a_wrong_sign: assert (!pv || S == S_exp);
`endif
`ifdef SANITY_LSEL
        a_wrong_lsel: assert (!pv || L == L_exp);
`endif
`ifdef SANITY_DELAY
        a_wrong_delay: assert (cnt < P - 1 || O0 == tq[39:20]);
`endif
`ifdef COVERS
        // score side (accum_mode = 0)
        c_load0:      cover (pv && p_load && !p_sub && S == 22'd0 && p_S != 22'd0);
        c_loadM_min:  cover (pv && p_load && p_sub && p_M == 22'h200000 && S == 22'h200000);
        c_load_prio:  cover (pv && p_load && p_se && !p_am && p_kb && p_qi != 0 && S == (p_sub ? p_M : 22'd0));
        c_sc_b7_add:  cover (pv && !p_am && p_se && !p_load && p_top && p_kb && !p_sub && p_qi == 8'h80
                             && S == p_S + 22'd16384);               // -128 * -128 * ... sign
        c_sc_b7_sub:  cover (pv && !p_am && p_se && !p_load && p_top && p_kb && p_sub && p_qi == 8'h7F
                             && S == p_S + 22'd16256);               // subtract of -128*127
        c_sc_b0_neg:  cover (pv && !p_am && p_se && !p_load && p_b0 && p_kb && !p_sub && p_qi == 8'h80
                             && S == p_S - 22'd128);
        c_sc_wrap:    cover (pv && !p_am && p_se && !p_load && p_S == 22'h1FFFFF && S[21]);
        c_sc_hold:    cover (pv && !p_se && !p_load && S == p_S && p_kb);
        c_sc_in_acc:  cover (pv && p_am && p_se && !p_load && p_ae && p_vb && S != p_S);
        // accumulate side (accum_mode = 1), followed to the head
        c_acc_load:   cover (age == P && trk_lo && O0 == trk && O0 == 20'hF8080);   // -255*128
        c_acc_add:    cover (age == P && !trk_lo && O0 == trk);
        c_acc_neg:    cover (cnt == P && O0[19] && tq[19:0] == O0);
        c_hold_score: cover (pv && !p_am && p_ae && cnt == P && O0 == tq[19:0]);   // ring holds while scoring
        // L
        c_L_first:    cover (pv && p_ae && p_b0 && p_sel0 && p_first && L == {4'd0, p_W} && p_L != L);
        c_L_add:      cover (pv && p_ae && p_b0 && p_sel0 && !p_first && p_W != 0 && L == p_L + {4'd0, p_W});
        c_L_wrap:     cover (pv && p_ae && p_b0 && p_sel0 && !p_first && L < p_L);
        c_L_sel_hold: cover (pv && p_ae && p_b0 && !p_sel0 && p_W != 0 && L == p_L);
        c_L_bit_hold: cover (pv && p_ae && !p_b0 && p_sel0 && p_W != 0 && L == p_L);
`endif
    end
endmodule
