// Formal harness for divider (SPEC.md sections 3 and 4). Top module of every SBY task.
// clk, rst_n, start, sum_in, denominator and shift are free inputs at every step. There are
// NO assumptions (no assume, restrict, anyconst or anyseq): the caller guarantees of the
// shipped configuration (SPEC A1-A4) are not assumed, they CONDITION the result assertion
// (a completion outside them is unspecified; everything else is asserted for all inputs).
// The DUT has no initial value: the .sby rejects any init attribute outside this harness.
//
// Configuration: -DP11 = LATCH_DENOMINATOR 1, CHECK_INVALID 1 (the defaults); otherwise 0/0
// (the shipped configuration). fv_mode.vh (written by run_all.sh) defines GATE for a
// gate-level netlist, which has no parameters.
//
// Task kinds:
//   PROTO   black box: protocol, latency, busy/done, ignored starts, reset, hold, shift,
//           completion-overrides-shift (the completion VALUE is not checked). Any DUT.
//   WB      everything in PROTO plus a_comp (the result after a completion equals the
//           independent reference ref_divider_seq.v), made inductive by white-box lemmas on
//           the golden's per-step partial remainder / quotient (wb_* wires, connected to the
//           DUT's internal registers by `connect` in the .sby). Golden-named RTL only.
//   COVERS, SANITY_*  see the bottom.
`include "fv_mode.vh"
module divider_props (
    input wire               clk,
    input wire               rst_n,
    input wire               start,
    input wire signed [19:0] sum_in,
    input wire        [11:0] denominator,
    input wire               shift
);
`ifdef P11
    localparam LD = 1, CI = 1;
`else
    localparam LD = 0, CI = 0;
`endif
    wire busy, done;
    wire signed [11:0] result;
`ifdef GATE
    divider dut (.clk(clk), .rst_n(rst_n), .start(start), .sum_in(sum_in), .denominator(denominator),
                 .shift(shift), .busy(busy), .done(done), .result(result));
`else
    divider #(.LATCH_DENOMINATOR(LD), .CHECK_INVALID(CI)) dut (.clk(clk), .rst_n(rst_n),
                 .start(start), .sum_in(sum_in), .denominator(denominator), .shift(shift),
                 .busy(busy), .done(done), .result(result));
`endif

    // ---------------------------------------------------------------- protocol reference
    // Observer (initialised; never drives the DUT): a reset edge has been taken. Everything
    // is asserted from then on, whatever the power-up state was (R13).
    reg seen = 1'b0;
    // cnt: edges since the accept edge (0 = idle). An accept is an edge with rst_n, start and
    // cnt == 0; the completion edge is the one with cnt == 24 (the 24th edge after the accept).
    reg [4:0] cnt;
    reg       comp_p, rst_p, shift_p, start_p, busy_p, spec_p, done_p;
    reg signed [11:0] res_p;
    wire accept   = rst_n && cnt == 5'd0 && start;
    wire complete = rst_n && cnt == 5'd24;
    always @(posedge clk) begin
        if (!rst_n) seen <= 1'b1;
        cnt     <= !rst_n ? 5'd0 : cnt == 5'd0 ? {4'd0, start} : cnt == 5'd24 ? 5'd0 : cnt + 5'd1;
        comp_p  <= complete;
        rst_p   <= rst_n;
        shift_p <= shift;
        start_p <= start;
        busy_p  <= busy;
        done_p  <= done;
        res_p   <= result;
    end

`ifndef PROTO
    // ---------------------------------------------------------------- result reference
    wire signed [19:0] Sx;
    wire [11:0] Lx, rv;
    wire [23:0] rs, qs, Zx;
    wire rvalid, rtie;
    ref_divider_seq ref_div (.clk(clk), .load(accept), .step(rst_n && cnt >= 5'd1 && cnt <= 5'd23),
        .bitpos(5'd23 - cnt), .S_in(sum_in), .L_in(denominator), .S(Sx), .L(Lx), .rs(rs), .qs(qs),
        .Z(Zx), .valid(rvalid), .value(rv), .tie(rtie));
    // 0/0 only: A1, the denominator is the same at every edge from the accept edge to the
    // completion edge (lbad: it differed at one of the edges before the current one).
    reg lbad;
    always @(posedge clk)
        if (accept) lbad <= 1'b0;
        else if (cnt != 5'd0 && denominator != Lx) lbad <= 1'b1;
`ifdef P11
    wire spec_now = 1'b1;                                   // every request is specified
`else
    wire spec_now = rvalid && !lbad && denominator == Lx;   // A1-A4 hold for this request
`endif
    reg signed [11:0] ref_p;
    reg tie_p, rvalid_p, lzero_p;
    always @(posedge clk) begin
        spec_p   <= spec_now;
        ref_p    <= rv;
        tie_p    <= rtie && rvalid;
        rvalid_p <= rvalid;
        lzero_p  <= Lx == 12'd0;
    end
`endif

`ifndef SANITY_PU
    always @* if (seen) begin
        a_cnt:  assert (cnt <= 5'd24);                        // harness consistency
        a_busy: assert (busy == (cnt != 5'd0));               // R4, R5, R6 latency and busy
`ifdef SANITY_LAT
        a_wrong_lat: assert (done == (cnt == 5'd24));         // negative control: latency 23
`else
        a_done: assert (done == comp_p);                      // R4, R5: done pulse
`endif
        if (!rst_p) a_rst: assert (result == 12'sd0 && !done && !busy);          // R10
        if (rst_p && !comp_p && shift_p)  a_shift: assert (result == {res_p[10:0], 1'b0}); // R8
        if (rst_p && !comp_p && !shift_p) a_hold:  assert (result == res_p);     // R7
`ifndef PROTO
`ifdef SANITY_ROUND
        // negative control: a reference that truncates instead of rounding
        if (rst_p && comp_p && spec_p) a_wrong_round: assert (result == ref_trunc_p);
`elsif SANITY_STAB
        // negative control (0/0): claim the result even when the denominator moved (no A1)
        if (rst_p && comp_p && spec_p_nostab) a_wrong_stab: assert (result == ref_p);
`else
        if (rst_p && comp_p && spec_p) a_comp: assert (result == ref_p);      // R1, R2, R9, R12
`endif
`endif
    end
`endif

`ifdef WB
    // ---------------------------------------------------------------- white-box lemmas
    // Proof aid only (not requirements): the golden's per-step invariant. With cnt = c in
    // 1..24 the golden has done d = c - 1 restoring steps, so its quotient register holds the
    // unconsumed dividend bits on top of the quotient bits so far, and its remainder is the
    // partial remainder of the reference (which is aligned to bit 24 - c):
    //   quotient  == ((Z << (c-1)) | (qs >> (24-c)))[22:0]
    //   remainder == rs >> (24-c)
    // plus the control registers. Valid while the request is a real division (L != 0,
    // S != -2^19) and, at 0/0, while the denominator has not moved.
    wire [1:0]  wb_state;
    wire [4:0]  wb_step;
    wire [22:0] wb_quotient;
    wire [11:0] wb_remainder;
    wire        wb_negative;
`ifdef P11
    wire [11:0] wb_divisor;
    wire        wb_invalid;
`endif
    wire [4:0]  sh  = 5'd24 - cnt;
    wire [23:0] low = (24'd1 << sh) - 24'd1;               // bits not yet processed
    wire [47:0] zq  = {24'd0, Zx} << (cnt - 5'd1);
`ifdef P11
    wire okd = Lx != 12'd0 && Sx != -20'sd524288;
`else
    wire okd = Lx != 12'd0 && Sx != -20'sd524288 && !lbad;
`endif
    always @* if (seen) begin
        l_state: assert (wb_state == (cnt == 5'd0 ? 2'd0 : cnt <= 5'd23 ? 2'd1 : 2'd2));
        if (cnt != 5'd0) begin
            l_step: assert (wb_step == cnt - 5'd1);
            l_neg:  assert (wb_negative == Sx[19]);
`ifdef P11
            l_div:  assert (wb_divisor == Lx);
            l_inv:  assert (wb_invalid == (Lx == 12'd0 || Sx == -20'sd524288));
`endif
            if (okd) begin
                l_rlow: assert (((rs ^ Zx) & low) == 24'd0);   // reference: low bits untouched
                l_qlow: assert ((qs & low) == 24'd0);          // reference: no bit set early
                l_q23:  assert (!qs[23]);                       // Z < 2^23 once S != -2^19
                l_rbnd: assert ((rs >> sh) < {12'd0, Lx});     // partial remainder < L
                l_quot: assert (wb_quotient == (zq[22:0] | (qs >> sh)));
                l_rem:  assert ({12'd0, wb_remainder} == (rs >> sh));
            end
        end
    end
`endif

`ifdef SANITY_ROUND
    // truncating reference: m = q (no round-up bit)
    wire [11:0] tv = Sx[19] ? (~qs[11:0] + 12'd1) : qs[11:0];
    reg signed [11:0] ref_trunc_p;
    always @(posedge clk) ref_trunc_p <= tv;
`endif
`ifdef SANITY_STAB
    reg spec_p_nostab;
    always @(posedge clk) spec_p_nostab <= rvalid;
`endif
`ifdef SANITY_PU
    // negative control: the power-up state is a reset state (must be refuted: it is free)
    always @* if (!seen) a_wrong_pu: assert (result == 12'sd0 && !busy);
`endif

`ifdef COVERS
    reg ppl = 1'b0;   // observer: a step has passed
    always @(posedge clk) ppl <= 1'b1;
    always @* begin
        c_pu_busy:    cover (!seen && busy);                                    // free power-up state
        c_pu_result:  cover (!seen && result != 12'sd0);
        c_done_pos:   cover (seen && done && spec_p && result > 12'sd0);
        c_done_neg:   cover (seen && done && spec_p && result < 12'sd0);
        c_max:        cover (seen && done && spec_p && result == 12'sd2047);
        c_min:        cover (seen && done && spec_p && result == -12'sd2048);
        c_tie_neg:    cover (seen && done && spec_p && tie_p && result < 12'sd0); // -x.5 away from 0
        c_start_busy: cover (seen && busy && start && cnt >= 5'd2);             // ignored start
        c_shift_busy: cover (seen && busy_p && busy && shift_p && result != res_p);
        c_shift_done: cover (seen && done && shift_p && result != {res_p[10:0], 1'b0} && result != 12'sd0);
        c_b2b:        cover (seen && rst_p && done_p && start_p && busy);       // start in the done cycle
        c_abort:      cover (seen && ppl && !rst_p && busy_p);                  // reset while busy
        c_hold:       cover (seen && rst_p && !done && !busy && !shift_p && result != 12'sd0);
`ifdef P11
        // (result after reset is 0 until a first completion, so a non-zero result before an
        // invalid completion would need two divisions, beyond the depth; a_comp proves the 0)
        c_invalid:    cover (seen && done && !rvalid_p && !lzero_p);   // overflow or S = -2^19 completes
        c_lzero:      cover (seen && done && lzero_p);                 // L = 0 completes
`else
        c_unspec:     cover (seen && done && rst_p && !spec_p && result != 12'sd0);  // outside A1-A4
`endif
    end
`endif
endmodule
