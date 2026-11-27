// seq_eq item (SPEC.md section 6): sequential equivalence miter of the golden (module
// gold_attention_controller: the snapshot with every module renamed gold_*, by run_all.sh)
// against the candidate (module attention_controller), both driven by the same free inputs.
//
// Anchor: RESET ANCHORING. Both instances start in arbitrary, independent power-up states (no
// initial value on either; guarded in seq_eq.sby). They share rst_n, so the first reset edge
// (observer an) puts both in their reset state together. From then on every control output
// must be equal; IO0 when it is driven; out_bit whenever the golden's result register is a
// function of the inputs since the anchor (f_res). Freshness observers follow the golden's
// own control signals (read through `connect`, read-only) and mark which golden registers no
// longer depend on the power-up state:
//   f_ctl   pos, token, second_pass (set at the first accepted start after the anchor)
//   f_oi    output_index (set at the first run end)
//   f_nib   nibble bits, f_q Q-byte bits, f_S score, f_M maximum, f_L weight sum,
//   f_ring  ring slot j (rotates with the ring), f_req the divider request (head and L at the
//           accept edge, L since), f_res the divider result.
// A guard that is too weak only makes the proof fail, never pass wrongly: the observers are
// harness registers, and a_eq compares the candidate's PORTS with the golden's.
//   - There are NO assumptions (assume, restrict, anyconst, anyseq) anywhere.
//   - Optional candidate-supplied lemmas over gold.*, cand.* and the read-only observers are
//     included from seq_lemmas.vh (formal/lemma_prep.py). They are ASSERTIONS, never assumed.
// The golden's behaviour before the first reset, and a continue run without a completed fresh
// run's maximum (f_M = 0), are outside the contract (SPEC 2.4), so out_bit is not compared
// there.
`include "fv_mode.vh"
module ctrl_miter (
    input wire       clk,
    input wire       rst_n,
    input wire       start,
    input wire [3:0] last,
    input wire [3:0] score_shift,
    input wire       cont,
    input wire [3:0] spi_io,
    input wire       out_ready,
    input wire       out_shift
);
    localparam P = `P_OUTPUTS;
    wire g_idle, g_cs, g_sck, g_mosi, g_oe, g_valid, g_bit;
    wire c_idle, c_cs, c_sck, c_mosi, c_oe, c_valid, c_bit;
    gold_attention_controller #(.OUTPUTS(P)) gold (
        .clk(clk), .rst_n(rst_n), .start(start), .last(last), .score_shift(score_shift), .cont(cont),
        .idle(g_idle), .spi_cs_n(g_cs), .spi_sck(g_sck), .spi_mosi(g_mosi), .spi_mosi_oe(g_oe),
        .spi_io(spi_io), .out_valid(g_valid), .out_ready(out_ready), .out_shift(out_shift), .out_bit(g_bit));
`ifdef GATE
    attention_controller cand (
`else
    attention_controller #(.OUTPUTS(P)) cand (
`endif
        .clk(clk), .rst_n(rst_n), .start(start), .last(last), .score_shift(score_shift), .cont(cont),
        .idle(c_idle), .spi_cs_n(c_cs), .spi_sck(c_sck), .spi_mosi(c_mosi), .spi_mosi_oe(c_oe),
        .spi_io(spi_io), .out_valid(c_valid), .out_ready(out_ready), .out_shift(out_shift), .out_bit(c_bit));

    // golden control signals, tied by `connect` in seq_eq.sby (read-only)
    wire [2:0] g_state;
    wire [9:0] g_pos;
    wire g_rise, g_run_end, g_load, g_subtract, g_score_en, g_accum_mode, g_accum_en, g_first,
         g_load_o, g_men, g_mfirst, g_dstart;
    wire [2:0] g_bitsel;
    wire [$clog2(P)-1:0] g_sel;
    wire [1:0] g_dstate;

    reg an = 1'b0, f_ctl = 1'b0, f_oi = 1'b0, f_S = 1'b0, f_M = 1'b0, f_L = 1'b0, f_reqr = 1'b0, f_res = 1'b0;
    reg [3:0] f_nib = 4'd0;
    reg [7:0] f_q = 8'd0;
    reg [P-1:0] f_ring = {P{1'b0}};
    wire f_req = f_reqr && f_L;
    wire term_f = !g_accum_en || (f_S && f_nib[3]);        // W (from S) and the serial V bit
    wire head_f = (g_load_o || f_ring[0]) && term_f;        // the head's new sum in accumulate mode
    always @(posedge clk) begin
        if (!rst_n) an <= 1'b1;
        if (an && rst_n && g_idle && start) f_ctl <= 1'b1;
        if (an && rst_n && g_run_end) f_oi <= 1'b1;
        if (rst_n) f_nib <= {4{an}} & (g_rise ? 4'hF : {f_nib[2:0], 1'b1});
        if (rst_n && g_state == 3'd3 && !g_pos[3]) f_q <= {8{an}} & {f_q[6:0], f_nib[3]};
        // mac_unit and max_reg have no reset: they follow the golden's controls in every cycle
        if (g_load) f_S <= an && (g_subtract ? f_M : 1'b1);
        else if (g_score_en) f_S <= an && f_S && (g_accum_mode ? head_f : (&f_q && f_nib[3]));
        if (g_men) f_M <= an && f_S && (g_mfirst || f_M);
        f_ring <= {an && (g_accum_mode ? head_f : f_ring[0]), f_ring[P-1:1]};
        if (g_accum_en && g_sel == '0 && g_bitsel == 3'd0) f_L <= an && f_S && (g_first || f_L);
        if (rst_n && g_dstart && g_dstate == 2'd0) f_reqr <= an && f_ring[0] && f_L;
        else f_reqr <= f_req;
        if (!rst_n) f_res <= 1'b1;
        else if (g_dstate == 2'd2) f_res <= an && f_req;   // completion edge (ROUND)
    end

`ifndef SANITY_EQ
    // harness self-consistency: no observer is set before the anchor
    always @* a_obs: assert (an || !(f_ctl || f_oi || f_res || f_S || f_M || f_L || f_reqr
                                    || f_nib != 4'd0 || f_q != 8'd0 || f_ring != {P{1'b0}}));
`endif
    always @* if (an) begin
`ifdef SANITY_EQ
        a_wrong_eq: assert (c_mosi == g_mosi);   // negative control: IO0 compared while released
`else
        a_eq: assert (c_idle == g_idle && c_cs == g_cs && c_sck == g_sck && c_oe == g_oe
                      && c_valid == g_valid && (!g_oe || c_mosi == g_mosi) && (!f_res || c_bit == g_bit));
`endif
    end

`include "seq_lemmas.vh"
endmodule
