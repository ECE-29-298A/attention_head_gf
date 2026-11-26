// Formal harness for exp_lut (SPEC.md sections 3 and 4). Top module of every SBY task.
// clk, rst_n, start, D and shift are free inputs at every step. There are NO assumptions
// (no assume, restrict, anyconst or anyseq). The DUT has no initial value: the .sby rejects
// any init attribute outside this harness, so the DUT's state is free at step 0.
//
// Configuration: -DR0 (REGISTERED = 0) or -DR1 (REGISTERED = 1). fv_mode.vh (written by
// run_all.sh) defines GATE for a gate-level netlist, which has no parameter.
//
// Two formal references for W, both independent of the RTL's barrel shifter, guard bit and
// out-of-range logic. The only shared data is the generated include ref_table.vh, computed by
// model/golden_model.py from the mathematical definition (exp, exact rationals):
//   wA: D' by wide arithmetic, (D + 2^(shift-1)) >> shift on 23 bits (no overflow possible),
//       then ref_wtab(D') for D' < 64, else 0 (ref_wtab(k) = 0 for k >= 25).
//   wB: D' capped at 25 = the number of thresholds ref_thr(shift, k), k = 1..25, that D
//       reaches (ref_thr = smallest D with D' >= k, computed with exact rationals), then
//       ref_wtab(D'). No shift and no addition at all.
`include "fv_mode.vh"
module exp_lut_props (
    input wire        clk,
    input wire        rst_n,
    input wire        start,
    input wire [21:0] D,
    input wire [3:0]  shift
);
`include "ref_table.vh"
`ifdef R1
    localparam REG = 1;
`else
    localparam REG = 0;
`endif
    wire       done;
    wire [7:0] W;
`ifdef GATE
    exp_lut dut (.clk(clk), .rst_n(rst_n), .start(start), .D(D), .shift(shift), .done(done), .W(W));
`else
    exp_lut #(.REGISTERED(REG)) dut (.clk(clk), .rst_n(rst_n), .start(start), .D(D), .shift(shift), .done(done), .W(W));
`endif

    // ---------------------------------------------------------------- references
    wire [22:0] half = (shift == 4'd0) ? 23'd0 : (23'd1 << (shift - 4'd1));
    wire [22:0] sumA = {1'b0, D} + half;
    wire [22:0] dpA  = sumA >> shift;
    wire [7:0]  wA   = (dpA < 23'd64) ? ref_wtab(dpA[5:0]) : 8'd0;

    wire [25:1] ge;
    genvar gk;
    generate for (gk = 1; gk <= 25; gk = gk + 1) begin : g_thr
        assign ge[gk] = {1'b0, D} >= ref_thr(shift, gk);
    end endgenerate
    reg [5:0] dpB;
    integer i;
    always @* begin
        dpB = 6'd0;
        for (i = 1; i <= 25; i = i + 1) dpB = dpB + {5'd0, ge[i]};
    end
    wire [7:0] wB = ref_wtab(dpB);

`ifdef R0
    // ---------------------------------------------------------------- REGISTERED = 0
`ifdef SANITY_TRUNC
    // negative control: D' truncated instead of rounded half up (must be refuted)
    wire [22:0] dpT = {1'b0, D} >> shift;
    wire [7:0]  wT  = (dpT < 23'd64) ? ref_wtab(dpT[5:0]) : 8'd0;
    always @* a_wrong_trunc: assert (W == wT);
`elsif SANITY_D21
    // negative control: D[21] ignored (D read as 21 bits); must be refuted, because the
    // contract specifies W = 0 for every D >= 2^21 (SPEC R4)
    wire [22:0] sumN = {2'b0, D[20:0]} + half;
    wire [22:0] dpN  = sumN >> shift;
    wire [7:0]  wN   = (dpN < 23'd64) ? ref_wtab(dpN[5:0]) : 8'd0;
    always @* a_wrong_d21: assert (W == wN);
`else
    always @* begin
        a_wA:   assert (W == wA);        // R1..R5: W = f(D, shift), every input, any clk/rst_n/start
        a_wB:   assert (W == wB);        // the same against the second formulation
        a_done: assert (done == start);  // R7
    end
`endif
`ifdef COVERS
    genvar ck;
    generate for (ck = 0; ck <= 25; ck = ck + 1) begin : g_cdp
        always @* cover (dpA == ck && W == ref_wtab(ck));           // every D' 0..25
    end endgenerate
    generate for (ck = 1; ck <= 15; ck = ck + 1) begin : g_ctie
        // a rounding tie at every shift, rounded up, with a non-zero weight
        always @* cover (shift == ck && D[ck-1:0] == (22'd1 << (ck - 1)) && W == wA && W != 8'd0);
    end endgenerate
    always @* begin
        c_d20:      cover (D >= 22'h100000 && D < 22'h200000 && shift == 4'd15 && W == 8'd0);
        c_d21:      cover (D[21] && shift == 4'd15 && W == 8'd0);
        c_last_nz:  cover (shift == 4'd15 && D == 22'd802815 && W == 8'd1);   // 24*2^15 + 2^14 - 1
        c_first_z:  cover (shift == 4'd15 && D == 22'd802816 && W == 8'd0);   // 24*2^15 + 2^14
        c_done1:    cover (start && done && W == wA);
        c_done0:    cover (!start && !done && W == wA);
    end
`endif
`endif

`ifdef R1
    // ---------------------------------------------------------------- REGISTERED = 1
    // Observers (initialised harness registers; they never drive the DUT):
    reg pv = 1'b0;                 // at least one step has passed
    reg seen = 1'b0;               // a reset edge has been seen
    always @(posedge clk) begin
        pv <= 1'b1;
        if (!rst_n) seen <= 1'b1;
    end
    // Reference next state from the OBSERVED outputs (any state, also before any reset):
    //   done' = rst_n && start;  W' = !rst_n ? 0 : start ? wA : W
    reg [7:0] eW, pW, pwA, sW;
    reg       eD, prst, pst;
    always @(posedge clk) begin
        eW   <= !rst_n ? 8'd0 : start ? wA : W;
        eD   <= rst_n && start;
        pW   <= W;
        pwA  <= wA;
        prst <= rst_n;
        pst  <= start;
        // shadow (sequence) reference with the second formulation: after a reset, W equals
        // wB of the inputs at the most recent start, or 0 if none since the reset
        if (!rst_n) sW <= 8'd0;
        else if (start) sW <= wB;
    end
`ifdef SANITY_PU
    // negative control: W = 0 at power-up (must be refuted: the power-up state is free)
    always @* if (!pv) a_wrong_pu: assert (W == 8'd0);
`elsif SANITY_LAT0
    // negative control: zero latency, W follows the current inputs on a start (must be refuted)
    always @* if (pv && rst_n && start) a_wrong_lat0: assert (W == wA);
`else
    always @* if (pv) begin
        a_step_W:    assert (W == eW);                         // R8, R9, R10, R11
        a_step_done: assert (done == eD);                      // R12
        if (!prst)        a_rst:  assert (W == 8'd0 && !done); // R8
        if (prst && pst)  a_load: assert (W == pwA && done);   // R9
        if (prst && !pst) a_hold: assert (W == pW && !done);   // R10
    end
    always @* if (seen) a_seq: assert (W == sW);               // R11 (shadow, formulation B)
`endif
`ifdef COVERS
    reg       pdone = 1'b0;
    reg [2:0] nhold = 3'd0;
    reg       ppl = 1'b0;            // a load two steps back
    always @(posedge clk) begin
        pdone <= done;
        nhold <= (rst_n && !start) ? (nhold == 3'd7 ? nhold : nhold + 3'd1) : 3'd0;
        ppl <= pv && prst && pst;
    end
    always @* begin
        c_pu_nonzero: cover (!pv && W != 8'd0);                                // free power-up W
        c_pre_rst_ld: cover (pv && !seen && prst && pst && W == pwA && W != 8'd0); // load before any reset
        c_load_new:   cover (pv && prst && pst && W != pW && W != 8'd0);       // a load changes W
        c_load_zero:  cover (pv && prst && pst && pW != 8'd0 && W == 8'd0);    // a load of D' >= 25
        c_hold_diff:  cover (pv && prst && !pst && pwA != pW && W == pW);      // hold while inputs differ
        c_hold3:      cover (seen && nhold >= 3'd3 && W != 8'd0);              // 3 hold cycles after a load
        c_rst_start:  cover (pv && !prst && pst && pW != 8'd0 && W == 8'd0);   // reset wins over start
        c_b2b:        cover (pv && ppl && prst && pst && W != pW && pW != 8'd0); // back-to-back loads
        c_done_pulse: cover (pv && pdone && !done);                            // done falls after one cycle
        c_w255:       cover (seen && W == 8'd255);
    end
`endif
`endif
endmodule
