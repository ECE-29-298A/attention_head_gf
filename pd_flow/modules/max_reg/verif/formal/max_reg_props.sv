// Formal property harness for max_reg (SPEC.md section 4). No assumptions: clk, first, en
// and S_in are free inputs at every step, and the DUT's M has no initial value, so its
// power-up value is unconstrained (an arbitrary 22-bit value chosen by the solver).
// The only initialised registers are this harness's own observers (pv, loaded, nacc, ...),
// which start in "nothing observed yet"; they never drive the DUT.
//
// The reference compare is written twice, neither as the RTL's `S_in > M` on signed wires:
//   sgt_ob : offset-binary unsigned compare ({~a[21], a[20:0]} > {~b[21], b[20:0]})
//   sgt_df : sign of the 23-bit difference b - a (sign-extended operands)
// Property groups (one per SBY task, selected by define):
//   STEP     one-step next-state relation from any M                (R1 to R5)
//   SEQ      shadow running-max model: after a first load M == max   (R6, R7)
//   POWERUP  two DUT copies, independent power-up values: equal after a first load (R8)
//   COVERS   reachability / vacuity covers (both copies present)
//   SANITY_UNSIGNED, SANITY_POWERUP: wrong properties that MUST fail (negative controls)
module max_reg_props (
    input wire        clk,
    input wire        first,
    input wire        en,
    input wire [21:0] S_in
);
    localparam [21:0] MAXPOS = 22'h1FFFFF, MINNEG = 22'h200000, ALL1 = 22'h3FFFFF;

    wire [21:0] M;
    max_reg dut (.clk(clk), .first(first), .en(en), .S_in(S_in), .M(M));
`ifdef POWERUP
    wire [21:0] M2;
    max_reg dut2 (.clk(clk), .first(first), .en(en), .S_in(S_in), .M(M2));
`endif

    function automatic sgt_ob(input [21:0] a, input [21:0] b);   // a > b, signed
        sgt_ob = {~a[21], a[20:0]} > {~b[21], b[20:0]};
    endfunction
    function automatic sgt_df(input [21:0] a, input [21:0] b);   // a > b, signed
        reg [22:0] d;
        begin
            d = {b[21], b} - {a[21], a};                           // b - a, 23 bits, no overflow
            sgt_df = d[22];                                        // negative <=> a > b
        end
    endfunction

    // previous-cycle observers
    reg        pv = 1'b0;          // a previous cycle exists
    reg [21:0] Mp, Sp;
    reg        fp, ep;
    // reference decision and next state, computed from the current S_in and M and
    // registered, so each assertion compares registers bit by bit (this keeps the
    // inductive invariant small enough for abc pdr; k-induction does not need it)
    reg        gtp;                // sgt_ob(S_in, M) in the previous cycle
    reg [21:0] refn;               // reference next state computed in the previous cycle
    // shadow model of the sequence semantics (independent of the DUT's register)
    reg        loaded = 1'b0;      // a first load (en && first) has been observed
    reg [21:0] mx;                 // max of the scores accepted since the last first load
    reg [2:0]  nacc = 3'd0;        // accepted scores since the last first load (saturating)
    reg [2:0]  nhold = 3'd0;       // consecutive en = 0 cycles while loaded (saturating)
    reg        reloads = 1'b0;     // a second first load has been observed
    always @(posedge clk) begin
        pv <= 1'b1;
        Mp <= M; Sp <= S_in; fp <= first; ep <= en;
        gtp <= sgt_ob(S_in, M);
        refn <= (en && (first || sgt_ob(S_in, M))) ? S_in : M;
        if (en && first) begin
            reloads <= loaded;
            loaded <= 1'b1; mx <= S_in; nacc <= 3'd1;
        end else if (en && loaded) begin
            if (sgt_df(S_in, mx)) mx <= S_in;
            if (nacc != 3'd7) nacc <= nacc + 3'd1;
        end
        if (loaded && !en) begin if (nhold != 3'd7) nhold <= nhold + 3'd1; end
        else nhold <= 3'd0;
    end
    reg        gap = 1'b0;         // an en = 0 cycle seen since the last first load
    always @(posedge clk)
        if (en && first) gap <= 1'b0; else if (loaded && !en) gap <= 1'b1;
`ifdef POWERUP
    reg [21:0] M2p;
    always @(posedge clk) M2p <= M2;
`endif

    always @* begin
`ifdef STEP
        a_step:  assert (!pv || M == refn);                              // R1..R5 together
        a_hold:  assert (!(pv && !ep) || M == Mp);                       // R2: en = 0 holds
        a_first: assert (!(pv && ep && fp) || M == Sp);                  // R3: first overrides
        a_gt:    assert (!(pv && ep && !fp && gtp) || M == Sp);          // R4: greater loads
        a_le:    assert (!(pv && ep && !fp && !gtp) || M == Mp);         // R4, R5: <= holds (tie too)
`endif
`ifdef SEQ
        a_seq:   assert (!loaded || M == mx);                            // R7
        // R7: without a first load M never decreases: it holds or takes a strictly greater S_in
        a_mono:  assert (!(pv && !(ep && fp)) || M == Mp || (M == Sp && gtp));
        a_src:   assert (!pv || M == Mp || M == Sp);                     // M only ever takes S_in
`endif
`ifdef POWERUP
`ifndef SANITY_POWERUP
        a_pu:    assert (!loaded || M == M2);                            // R8
`else
        a_wrong_pu: assert (M == M2);      // negative control: power-up values are free
`endif
`endif
`ifdef SANITY_UNSIGNED
        // negative control: reference with an UNSIGNED compare; must be refuted
        a_wrong_unsigned: assert (!pv || M == ((ep && (fp || Sp > Mp)) ? Sp : Mp));
`endif
`ifdef COVERS
        // one-step regions, each observing M
        c_first_lower:   cover (pv && ep && fp && sgt_ob(Mp, Sp) && M == Sp);
        c_first_equal:   cover (pv && ep && fp && Sp == Mp && M == Sp);
        c_gt_update:     cover (pv && ep && !fp && sgt_ob(Sp, Mp) && M == Sp && M != Mp);
        c_tie_hold:      cover (pv && ep && !fp && Sp == Mp && M == Mp);
        c_lt_hold:       cover (pv && ep && !fp && sgt_ob(Mp, Sp) && M == Mp);
        c_en0_greater:   cover (pv && !ep && !fp && sgt_ob(Sp, Mp) && M == Mp);
        c_en0_first:     cover (pv && !ep && fp && Sp != Mp && M == Mp);
        // signed compare corners (unsigned order would disagree)
        c_neg_vs_pos:    cover (pv && ep && !fp && Sp[21] && !Mp[21] && M == Mp);
        c_pos_vs_neg:    cover (pv && ep && !fp && !Sp[21] && Mp[21] && M == Sp);
        c_max_over_min:  cover (pv && ep && !fp && Sp == MAXPOS && Mp == MINNEG && M == MAXPOS);
        c_min_vs_max:    cover (pv && ep && !fp && Sp == MINNEG && Mp == MAXPOS && M == MAXPOS);
        c_min_tie:       cover (pv && ep && !fp && Sp == MINNEG && Mp == MINNEG && M == MINNEG);
        c_max_tie:       cover (pv && ep && !fp && Sp == MAXPOS && Mp == MAXPOS && M == MAXPOS);
        c_zero_over_m1:  cover (pv && ep && !fp && Sp == 22'd0 && Mp == ALL1 && M == 22'd0);
        c_m1_vs_zero:    cover (pv && ep && !fp && Sp == ALL1 && Mp == 22'd0 && M == 22'd0);
        c_min_over_max_first: cover (pv && ep && fp && Sp == MINNEG && Mp == MAXPOS && M == MINNEG);
        // sequences
        c_seq3_not_last: cover (loaded && nacc >= 3'd3 && pv && ep && !fp && sgt_df(mx, Sp) && M == mx);
        c_reload_lower:  cover (reloads && pv && ep && fp && sgt_df(Mp, Sp) && M == Sp);
        c_hold4:         cover (loaded && nhold >= 3'd4 && M == mx);
        c_preload_update:cover (!loaded && pv && ep && !fp && M != Mp);    // before any first load
        c_ctrl_pattern:  cover (loaded && gap && nacc >= 3'd2 && pv && ep && !fp
                                && M == Sp && M != Mp);   // after an en = 0 gap, a later key raises M
        // power-up independence: copies start different and converge at the first load
        c_pu_differ:     cover (!pv && M != M2);
        c_pu_converge:   cover (pv && ep && fp && Mp != M2p && M == M2);   // differ, then a first load
`endif
    end
endmodule
