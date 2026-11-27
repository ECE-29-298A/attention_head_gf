// Golden-internal properties of attention_controller (SPEC.md section 5).
// run_all.sh inserts `include "ctrl_int_props.vh" before the endmodule of a COPY of the golden
// snapshot/attention_controller.sv (the snapshot itself is never edited) and reads that copy
// with -formal; the submodules are the frozen golden files, read WITHOUT -formal.
// These items apply to the golden only (they name its internal signals); a candidate inherits
// them through equiv_P (eqy_rtl OR seq_eq) and is checked at its ports by fv_ports_P.
// No assume / restrict / anyconst anywhere: every input is free at every step. Properties are
// reset-anchored (f_rs: a reset edge has been seen) and, where the SPEC says so, conditioned on
// the host holding last/score_shift/cont during the run (f_h; discharged at the TT top by
// fv_top). -DCOVERS selects the covers instead of the assertions; -DSANITY_<x> one negative
// control (a deliberately wrong assertion that must be refuted).
`ifdef FORMAL
    localparam int VB = 8 * OUTPUTS;             // clocks in one V block
    localparam [9:0] LPOS = 10'(7 * OUTPUTS);    // the block's L update: sel = 0, bit_sel = 0
    localparam [31:0] CMDW = 32'h6B00_0000;      // command + 24-bit address, MSB first
    localparam [31:0] CMDW_WRONG = 32'hEB00_0000;
    reg f_pv = 1'b0;            // $past valid
    reg f_rs = 1'b0;            // a reset edge has occurred
    reg f_okr = 1'b0;           // previous cycle: f_rs and rst_n
    reg f_rsr = 1'b0;           // previous cycle: f_rs and !rst_n (a reset edge after a reset)
    reg f_run = 1'b0;           // a start was accepted since the last reset edge
    reg f_held = 1'b0;          // last/score_shift/cont unchanged since the accepted start
    reg [3:0] f_last, f_shift;
    reg f_cont;
    reg [4:0] f_vcnt;           // V blocks completed in this run
    reg [12:0] f_lsum;          // mirror of L by the SPEC rule (no wrap: 13 bits)
    reg [7:0] f_wmax;           // largest weight of this run's V blocks
    reg f_lv = 1'b0;            // L has been written with first = 1: L == f_lsum from then on
    reg [11:0] f_lacc;          // L at the divider accept edge
    reg [3:0] f_cap;            // IO3..IO0 at the last SCK rise
    wire f_h = f_held && last == f_last && score_shift == f_shift && cont == f_cont;
    wire f_accept = rst_n && state == DIV_START && pos[P-1:0] == output_index && !div_busy;
    wire f_lupd = state == VALUE && pos == LPOS;  // SPEC A2a: one L update per V block
    wire f_p2 = state == SCORE && second_pass;
    wire f_dio = state == DIV_START || state == DIV_WAIT || state == OUTPUT;

    // independent port reference (formal/ref_ctrl.v) on the same inputs (SPEC 5.5)
    wire r_idle, r_cs_n, r_sck, r_oe, r_mosi, r_valid, r_pass2, r_rowend;
    wire [2:0] r_seg, r_comp, r_ring;
    wire [10:0] r_c;
    wire [3:0] r_tok;
    ctrl_ref #(.P(OUTPUTS)) f_ref (
        .clk(clk), .rst_n(rst_n), .start(start), .last(last), .cont(cont), .out_ready(out_ready),
        .r_idle(r_idle), .r_cs_n(r_cs_n), .r_sck(r_sck), .r_oe(r_oe), .r_mosi(r_mosi), .r_valid(r_valid),
        .r_seg(r_seg), .r_c(r_c), .r_tok(r_tok), .r_pass2(r_pass2), .r_rowend(r_rowend),
        .r_comp(r_comp), .r_ring(r_ring));
    // divider_unit.state / .step, tied by `connect` after flatten (ctrl_int.sby)
    wire [1:0] f_dstate;
    wire [4:0] f_dstep;
    always @(posedge clk) begin
        f_pv <= 1'b1;
        f_okr <= f_rs && rst_n;
        f_rsr <= f_rs && !rst_n;
        if (!rst_n) begin f_rs <= 1'b1; f_run <= 1'b0; end
        if (rst_n && idle && start) begin
            f_run <= f_rs; f_held <= 1'b1; f_last <= last; f_shift <= score_shift; f_cont <= cont;
            f_vcnt <= 5'd0;
        end else if (!f_h) f_held <= 1'b0;
        if (rst_n && state == VALUE && pos == 10'(VB - 1)) f_vcnt <= f_vcnt + 5'd1;
        if (f_lupd) begin  // mirrors the SPEC rule, with or without reset (mac_unit has none)
            f_lsum <= (token == 4'd0 ? 13'd0 : f_lsum) + {5'd0, weight};
            f_wmax <= (token == 4'd0 || weight > f_wmax) ? weight : f_wmax;
            if (token == 4'd0 && f_rs) f_lv <= 1'b1;
        end
        if (f_accept) f_lacc <= weight_sum;
        if (rst_n && rise) f_cap <= spi_io;
    end

`ifndef COVERS
    // ---------------------------------------------------------------- invariants (always)
`ifndef SANITY_ANY
    always @* o_obs: assert (f_rs || (!f_lv && !f_run && !f_okr && !f_rsr));  // observers start with the reset
`endif
    always @* if (f_rs) begin
`ifndef SANITY_ANY
        j_restart: assert (state != RESTART || (pos == 10'd0 && !flash_open && token == 4'd0 && !second_pass));
        j_cmd:     assert (state != CMD || (pos >= 10'd1 && pos <= 10'd161 && flash_open && token == 4'd0 && !second_pass));
        j_value:   assert (state != VALUE || (pos < 10'(VB) && second_pass));
        j_dio:     assert (!f_dio || second_pass);
        j_div:     assert ((div_busy || div_done) == (state == DIV_WAIT));          // R-DIV1
        j_sdone:   assert (!score_done || (pos == 10'd0 && (state == VALUE || (state == SCORE && !second_pass))));
        // SPI pins (SPEC 3)
        s_sck:  assert (spi_sck == (((state == SCORE || state == VALUE) && pos[1:0] == 2'd0)
                                    || (state == CMD && pos[1:0] == 2'd2)));
        s_oe:   assert (spi_mosi_oe == (state == CMD && pos < 10'd128));
        s_mosi: assert (!(state == CMD && pos < 10'd128) || spi_mosi == CMDW[5'd31 - pos[6:2]]);
        s_cs:   assert (spi_cs_n == !flash_open);
        s_out:  assert (out_valid == (state == OUTPUT) && idle == (state == IDLE) && out_bit == result[11]);
        // data capture: the serial bit is the captured nibble, MSB first (SPEC 3.4)
        s_cap:  assert (!(state == SCORE || state == VALUE)
                        || (pos[1:0] == 2'd0 && nibble == f_cap)
                        || (pos[1:0] == 2'd1 && nibble[3:1] == f_cap[2:0])
                        || (pos[1:0] == 2'd2 && nibble[3:2] == f_cap[1:0])
                        || (pos[1:0] == 2'd3 && nibble[3] == f_cap[0]));
        // fv_ports: the control pins equal the independent reference (SPEC 3, 5.5)
        a_ports: assert (idle == r_idle && spi_cs_n == r_cs_n && spi_sck == r_sck
                         && spi_mosi_oe == r_oe && out_valid == r_valid && (!r_oe || spi_mosi == r_mosi));
        // relational invariants golden <-> reference (they close the induction of a_ports)
        r_map:  assert (r_seg == state && r_cs_n == spi_cs_n);
        r_cnt:  assert ((state != CMD || r_c + 11'd1 == {1'b0, pos})
                        && (!(state == SCORE || state == VALUE) || r_c == {1'b0, pos}));
        r_tokp: assert (state == IDLE || (r_tok == token && r_pass2 == second_pass));
        r_rend: assert (r_rowend == (score_done && !second_pass));
        r_ph:   assert (!(state == SCORE || state == VALUE || f_dio) || r_ring == 3'(pos[P-1:0]));
        r_oi:   assert (!f_dio || r_comp == 3'(output_index));
        r_dw:   assert (state != DIV_WAIT
                        || (r_c <= 11'd22 && f_dstate == 2'd1 && {6'd0, f_dstep} == r_c)
                        || (r_c == 11'd23 && f_dstate == 2'd2)
                        || (r_c == 11'd24 && f_dstate == 2'd0 && div_done));
        // A1: the divider's denominator is constant from the accept edge to the completion edge
        a1_stable: assert (!div_busy || weight_sum == f_lacc);
        // A2a support: L equals the SPEC sum of this run's weights; no 12-bit wrap
        l_mirror: assert (!f_lv || weight_sum == f_lsum[11:0]);
        l_p2:     assert (!((f_p2 || (state == VALUE && pos <= LPOS)) && token != 4'd0)
                          || (f_lv && f_lsum <= 13'd255 * {9'd0, token} && f_wmax <= f_lsum));
        l_after:  assert (!((state == VALUE && pos > LPOS) || f_dio)
                          || (f_lv && f_lsum <= 13'd255 * ({9'd0, token} + 13'd1) && f_wmax <= f_lsum));
        if (f_run && f_h) begin
            v_tok_le:  assert (!(state == SCORE || state == VALUE) || token <= last);
            v_cnt_p1:  assert (!(state == RESTART || state == CMD || (state == SCORE && !second_pass)) || f_vcnt == 5'd0);
            v_cnt_p2:  assert (!(f_p2 || state == VALUE) || {1'b0, token} == f_vcnt);
            v_cnt_end: assert (!f_dio || {1'b0, token} + 5'd1 == f_vcnt);
        end
        if (f_run && f_h) begin
            v_tok_end: assert (!f_dio || token == last);
            // A2a: at every accept edge L = sum of the W of tokens 0..last of this run, each once,
            // hence L >= every one of them (SPEC 6)
            a2a_sum: assert (!f_accept || (weight_sum == f_lsum[11:0] && weight_sum >= f_wmax
                                           && f_vcnt == {1'b0, last} + 5'd1));
        end
`endif
    end

    // ---------------------------------------------------------------- transitions and steps
    // f_ok: the previous edge was an ordinary (rst_n = 1) edge after a reset (f_okr, below)
    wire f_ok = f_okr;
    always @(posedge clk) if (f_pv) begin
`ifndef SANITY_ANY
        t_reset: assert (!$past(!rst_n) || (state == IDLE && !flash_open && !spi_sck && !score_done
                                            && !div_busy && !div_done && result == 12'd0));
        if (f_ok) begin
            case ($past(state))
            IDLE: if (!$past(start)) begin
                    t_idle_hold: assert (state == IDLE && flash_open == $past(flash_open));
                end else if (!$past(cont)) begin
                    t_idle_fresh: assert (state == RESTART && pos == 10'd0 && token == 4'd0 && !second_pass && !flash_open);
                end else begin
                    t_idle_cont: assert (state == SCORE && pos == 10'd0 && token == 4'd0 && second_pass
                                         && flash_open == $past(flash_open) && spi_sck);
                end
            RESTART: t_restart: assert (state == CMD && pos == 10'd1 && flash_open);
            CMD: if ($past(pos) == 10'd161) begin
                    t_cmd_end: assert (state == SCORE && pos == 10'd0 && flash_open);
                end else begin
                    t_cmd_step: assert (state == CMD && pos == $past(pos) + 10'd1);
                end
            SCORE: if ($past(&pos && second_pass)) begin
                    t_score_value: assert (state == VALUE && pos == 10'd0 && score_done);
                end else begin
                    t_score_step: assert (state == SCORE && pos == $past(pos) + 10'd1
                                          && score_done == $past(&pos));
                end
            VALUE: if ($past(pos) == 10'(VB - 1)) begin
                    if ($past(token == last)) begin
                        t_value_div: assert (state == DIV_START && pos == 10'd0 && output_index == '0 && token == $past(token));
                    end else begin
                        t_value_next: assert (state == SCORE && pos == 10'd0 && token == $past(token) + 4'd1);
                    end
                end else begin
                    t_value_step: assert (state == VALUE && pos == $past(pos) + 10'd1 && token == $past(token)
                                          && score == $past(score));  // S (hence D) held in VALUE
                end
            DIV_START: if ($past(pos[P-1:0] == output_index)) begin
                    t_ds_go: assert (state == DIV_WAIT && div_busy && output_index == $past(output_index));
                end else begin
                    t_ds_wait: assert (state == DIV_START && output_index == $past(output_index));
                end
            DIV_WAIT: if ($past(div_done)) begin
                    t_dw_done: assert (state == OUTPUT);
                end else begin
                    t_dw_wait: assert (state == DIV_WAIT);
                end
            OUTPUT: if ($past(out_ready)) begin
                    t_out_next: assert (output_index == $past(output_index) + 1'b1
                                        && state == ($past(&output_index) ? IDLE : DIV_START));
                end else begin
                    t_out_hold: assert (state == OUTPUT && output_index == $past(output_index));
                end
            default: ;
            endcase
            // pass 1: one max_reg update per row, in token order; the last row starts pass 2
            if ($past(score_done && !second_pass)) begin
                t_p1_tok: assert (token == ($past(token == last) ? 4'd0 : $past(token) + 4'd1)
                                  && second_pass == $past(token == last));
            end
            // S after the row's 8 load clocks: 0 in pass 1, M in pass 2 (SPEC 4.3)
            if ($past(state == SCORE && pos == 10'd7)) begin
                t_load: assert (score == ($past(second_pass) ? maximum : 22'sd0) && maximum == $past(maximum));
            end
            // ring phase: from the first V bit to the last accept, pos[P-1:0] steps by 1 mod P
            if ($past(state) != IDLE && $past(state) != RESTART && $past(state) != CMD) begin
                q_phase: assert (pos[P-1:0] == $past(pos[P-1:0]) + 1'b1);
            end
            // weight constant in a V block when score_shift is held (A4 support)
            if ($past(state == VALUE) && state == VALUE && $past(f_h) && f_h) begin
                q_weight: assert (weight == $past(weight));
            end
            // serial output: result changes only by a completion or by an out_shift in OUTPUT
            if (!div_done) begin
                o_shift: assert (result == ($past(out_shift && state == OUTPUT) ? {$past(result[10:0]), 1'b0} : $past(result)));
            end
        end
`endif
`ifdef SANITY_MOSI   // wrong: the command is 0xEB (Quad I/O read) instead of 0x6B (must be refuted)
        if (f_rs && state == CMD && pos < 10'd128) n_mosi: assert (spi_mosi == CMDW_WRONG[5'd31 - pos[6:2]]);
`endif
`ifdef SANITY_CAP    // wrong: the serial bit is IO0 of the nibble instead of IO3 (must be refuted)
        if (f_rs && state == SCORE && pos[1:0] == 2'd0) n_cap: assert (nibble[3] == f_cap[0]);
`endif
`ifdef SANITY_SCK     // wrong: SCK also high in phase 2 of the data clocks (must be refuted)
        if (f_rs && state == SCORE && pos[1:0] == 2'd2) n_sck: assert (spi_sck);
`endif
    end
`else
    // ---------------------------------------------------------------- covers (reset-anchored)
    // Every transition of the FSM, a reset from every non-idle state, a shift and both CS#
    // edges, each AFTER a reset. A witness must hold a 1024-clock score row, which smtbmc
    // cannot reach in time, so each cover sets a sticky bit and a group task asserts that not
    // all bits of its group (mask CV_MASK) are set: abc bmc3 refuting that assertion IS a
    // trace that reaches every cover of the group (run_all.sh checks the trace and the bits).
    localparam int NCV = 30;
    reg [2:0] f_pst;
    reg f_pdl, f_pdn, f_pshift, f_pcs, f_prs;
    always @(posedge clk) begin
        f_pst <= state;
        f_pdl <= score_done && !second_pass && token == last;
        f_pdn <= score_done && !second_pass && token != last;
        f_pshift <= state == OUTPUT && out_shift;
        f_pcs <= spi_cs_n;
        f_prs <= f_rs;
    end
    wire [NCV-1:0] cv;
    assign cv[0]  = f_okr && f_pst == IDLE && state == IDLE;          // c_idle_hold
    assign cv[1]  = f_okr && f_pst == IDLE && state == RESTART;       // c_idle_fresh
    assign cv[2]  = f_okr && f_pst == IDLE && state == SCORE;         // c_idle_cont
    assign cv[3]  = f_okr && f_pst == RESTART && state == CMD;        // c_restart
    assign cv[4]  = f_okr && f_pst == CMD && state == CMD;            // c_cmd_step
    assign cv[5]  = f_okr && f_pst == CMD && state == SCORE;          // c_cmd_end
    assign cv[6]  = f_okr && f_pst == SCORE && state == SCORE;        // c_score_step
    assign cv[7]  = f_okr && f_pdl && second_pass;                    // c_p1_last (pass 1 -> pass 2)
    assign cv[8]  = f_okr && f_pdn && !second_pass;                   // c_p1_next (next pass-1 token)
    assign cv[9]  = f_okr && f_pst == SCORE && state == VALUE;        // c_score_value
    assign cv[10] = f_okr && f_pst == VALUE && state == VALUE;        // c_value_step
    assign cv[11] = f_okr && f_pst == VALUE && state == SCORE;        // c_value_next
    assign cv[12] = f_okr && f_pst == VALUE && state == DIV_START;    // c_value_div
    assign cv[13] = f_okr && f_pst == DIV_START && state == DIV_START; // c_ds_wait (phase wait)
    assign cv[14] = f_okr && f_pst == DIV_START && state == DIV_WAIT; // c_ds_go
    assign cv[15] = f_okr && f_pst == DIV_WAIT && state == DIV_WAIT;  // c_dw_wait
    assign cv[16] = f_okr && f_pst == DIV_WAIT && state == OUTPUT;    // c_dw_done
    assign cv[17] = f_okr && f_pst == OUTPUT && state == OUTPUT;      // c_out_hold
    assign cv[18] = f_okr && f_pst == OUTPUT && state == DIV_START;   // c_out_next
    assign cv[19] = f_okr && f_pst == OUTPUT && state == IDLE;        // c_out_idle
    assign cv[20] = f_okr && f_pshift && state == OUTPUT;             // c_out_shift
    assign cv[21] = f_okr && f_pcs && !spi_cs_n;                      // c_cs_fall
    assign cv[22] = f_prs && !f_pcs && spi_cs_n;                      // c_cs_rise
    assign cv[23] = f_rsr && f_pst == RESTART;                        // c_rst_restart
    assign cv[24] = f_rsr && f_pst == CMD;                            // c_rst_cmd
    assign cv[25] = f_rsr && f_pst == SCORE;                          // c_rst_score
    assign cv[26] = f_rsr && f_pst == VALUE;                          // c_rst_value
    assign cv[27] = f_rsr && f_pst == DIV_START;                      // c_rst_ds
    assign cv[28] = f_rsr && f_pst == DIV_WAIT;                       // c_rst_dw
    assign cv[29] = f_rsr && f_pst == OUTPUT;                         // c_rst_out
    reg [NCV-1:0] f_hit = '0;
    always @(posedge clk) f_hit <= f_hit | cv;
    wire [NCV-1:0] f_mask = `CV_MASK;
    always @* w_group: assert ((f_hit & f_mask) != f_mask);
`endif
`endif
