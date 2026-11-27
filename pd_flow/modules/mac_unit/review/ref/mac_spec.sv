// Agent 2 independent reference for mac_unit (OUTPUTS = 8), written from review/EXPECTED.md.
// Shares no code with the golden: the ring is a circular buffer with a rotating head pointer
// (no shifting), the arithmetic is integer multiply by a signed bit weight (-128 for bit 7, 2^b
// otherwise) instead of shift + one's-complement add.
// Start state: the DUT's registers are FREE at step 0 (no reset exists). The reference state is
// constrained at step 0 only (assume under $initstate) to correspond to the DUT state: this is the
// "for any start state" mapping, not a constraint on the DUT. All later checks are assertions.
// w_ring is connected to dut.ring by the SBY script (connect -set, after flatten).
module mac_spec (
    input wire clk,
    input wire accum_mode, load, subtract, score_en, first, accum_en,
    input wire [21:0] M,
    input wire [7:0] qi, ki, W, v,
    input wire [2:0] sel, bit_sel
);
    wire signed [21:0] S;
    wire [11:0] L;
    wire signed [19:0] O0;
`ifdef GATE
    mac_unit dut (
`else
    mac_unit #(.OUTPUTS(8)) dut (
`endif.clk(clk), .accum_mode(accum_mode), .load(load), .subtract(subtract),
        .M(M), .score_en(score_en), .qi(qi), .ki(ki), .first(first), .accum_en(accum_en), .W(W),
        .sel(sel), .v(v), .bit_sel(bit_sel), .S(S), .L(L), .O0(O0));
    wire [159:0] w_ring;

    // ---------------- reference state ----------------
    reg [19:0] buf0, buf1, buf2, buf3, buf4, buf5, buf6, buf7; // circular buffer, slot = absolute index
    reg [2:0] hp;                                               // slot holding the current head
    reg [21:0] rS;
    reg [11:0] rL;

    function [19:0] slot(input [2:0] i);
        case (i)
            3'd0: slot = buf0; 3'd1: slot = buf1; 3'd2: slot = buf2; 3'd3: slot = buf3;
            3'd4: slot = buf4; 3'd5: slot = buf5; 3'd6: slot = buf6; default: slot = buf7;
        endcase
    endfunction

    // ---------------- reference next state (integers) ----------------
    integer wt, head, contrib, base, nS, nH, nL;
    always @* begin
        wt = (bit_sel == 3'd7) ? -128 : (1 << bit_sel);           // two's-complement bit weight
        head = $signed(slot(hp));                                  // 20-bit signed head value
        if (accum_mode) begin
            contrib = (accum_en && v[bit_sel]) ? $signed({24'd0, W}) * wt : 0;
            base = (accum_en && first && bit_sel == 3'd7) ? 0 : head;
            nH = base + contrib;                                   // new head (low 20 bits kept)
            nS = nH;                                               // what score_en would store
        end else begin
            contrib = ki[bit_sel] ? $signed(qi) * wt : 0;
            nS = subtract ? $signed(rS) - contrib : $signed(rS) + contrib;
            nH = head;                                             // adder busy: head unchanged
        end
        nL = (first ? 0 : rL) + W;
    end

    always @(posedge clk) begin
        case (hp)
            3'd0: buf0 <= nH[19:0]; 3'd1: buf1 <= nH[19:0]; 3'd2: buf2 <= nH[19:0]; 3'd3: buf3 <= nH[19:0];
            3'd4: buf4 <= nH[19:0]; 3'd5: buf5 <= nH[19:0]; 3'd6: buf6 <= nH[19:0]; default: buf7 <= nH[19:0];
        endcase
        hp <= hp + 3'd1;
        if (load) rS <= subtract ? M : 22'd0;
        else if (score_en) rS <= nS[21:0];
        if (accum_en && sel == 3'd0 && bit_sel == 3'd0) rL <= nL[11:0];
    end

    // ---------------- correspondence ----------------
    // DUT ring element k (bits 20k+19:20k) == reference slot (hp + k) mod 8.
    wire [7:0] corr;
    genvar k;
    generate for (k = 0; k < 8; k = k + 1) begin : g_corr
        assign corr[k] = w_ring[20*k +: 20] == slot(hp + k);
    end endgenerate
    wire state_match = &corr && S == rS && L == rL;

    always @* begin
        if ($initstate) assume (state_match); // start-state mapping (reference side only)
        // outputs, every cycle including step 0
        a_O0: assert (O0 == slot(hp));
        a_S:  assert (S == rS);
        a_L:  assert (L == rL);
        // full state correspondence (also the induction invariant)
        a_state: assert (state_match);
    end

`ifdef REF_COVERS
    // non-vacuity covers (reachable from a free state)
    always @* begin
        c_load_neg: cover (accum_mode && accum_en && first && bit_sel == 3'd7 && v[7] && W == 8'd255);
        c_L_upd:    cover (accum_en && sel == 3'd0 && bit_sel == 3'd0 && !first);
        c_sub_top:  cover (!accum_mode && subtract && bit_sel == 3'd7 && ki[7] && qi == 8'h80);
        c_bypass:   cover (!accum_mode && accum_en);
    end
`endif
endmodule
