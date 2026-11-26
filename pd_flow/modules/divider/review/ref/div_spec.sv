`default_nettype none
// Agent 2 independent formal reference for divider (from EXPECTED.md, written before reading verif/).
//
// Two references, both stated without the golden's algorithm:
//  (1) NONRESTORING (always): a radix-2 non-restoring divider in lockstep with a 0..24 protocol
//      counter. Signed partial remainder nr_r in [-L, L), quotient bit = (new nr_r >= 0), one final
//      correction R = nr_r < 0 ? nr_r + L : nr_r, round up when 2R >= L, sign applied as -(q+up).
//      Range (CHECK = 1): from its own quotient, Qm <= 2047 (O >= 0) or <= 2048 (O < 0). The
//      multiplicative in_range() of EXPECTED R2 is the CHECK = 0 domain assumption.
//  (2) EDGE = 1: the multiplicative bracket of EXPECTED R1, (2Q-1)L <= 32|O| < (2Q+1)L, checked on
//      the golden's result for a fixed table of edge/spot operand pairs (BMC; the operands are
//      constants per branch, so the multiplier is cheap). This anchors (1) to the specification.
// Protocol (P1..P7): busy, done, reset, hold, shift, completion-over-shift, ignored starts.
// Domain (assumed only for the chip configuration bits, at the accept / while busy):
//   CHECK == 0 -> the exactly rounded result is in range (implies L >= 1 and O != -524288)
//   LATCH == 0 -> denominator equals its accepted value while busy
// WB = 1 adds white-box lemmas (inv_*) relating the golden registers to the reference, so that
// k-induction closes; they are asserted, never assumed. Probes are connected by run_ref.sh with
// "connect -set" after flatten (Yosys has no hierarchical references).
`include "edge_n.vh"
module div_spec #(parameter LATCH = 0, parameter CHECK = 0, parameter WB = 1, parameter EDGE = 0, parameter RELAX_INV = 0) (
    input wire clk, input wire rst_n, input wire start,
    input wire signed [19:0] sum_in, input wire [11:0] denominator, input wire shift
);
    wire busy, done;
    wire signed [11:0] result;
    divider #(.LATCH_DENOMINATOR(LATCH), .CHECK_INVALID(CHECK)) dut (
        .clk(clk), .rst_n(rst_n), .start(start), .sum_in(sum_in), .denominator(denominator),
        .shift(shift), .busy(busy), .done(done), .result(result));

    function automatic in_range(input signed [19:0] o, input [11:0] l);
        reg [27:0] twoz, lw;
        begin
            twoz = {8'd0, (o < 0) ? -{o[19], o} : {1'b0, o}} * 28'd32;   // 32*|O| < 2^25
            lw = {16'd0, l};
            in_range = (o < 0) ? (twoz < 28'd4097 * lw) : (twoz < 28'd4095 * lw);
        end
    endfunction

    reg init = 1'b1;
    reg [4:0] cnt = 5'd0;
    reg signed [19:0] O_s = 20'sd0;
    reg [11:0] L_s = 12'd0;
    reg p_rst_n = 1'b0, p_shift = 1'b0, p_fin = 1'b0;
    reg [11:0] p_result = 12'd0, p_ref = 12'd0;
    // non-restoring reference state
    reg signed [15:0] nr_r = 16'sd0;
    reg [22:0] nr_z = 23'd0;      // dividend bits still to consume, MSB first (shifted left)
    reg [22:0] nr_q = 23'd0;      // quotient bits so far (shifted in at bit 0)
    wire accept = rst_n && cnt == 5'd0 && start;
    wire [20:0] a_in = sum_in[19] ? -{sum_in[19], sum_in} : {1'b0, sum_in};
    wire [20:0] a_s = O_s[19] ? -{O_s[19], O_s} : {1'b0, O_s};
    wire signed [15:0] Ls16 = $signed({4'd0, L_s});
    wire signed [15:0] nr_2r = (nr_r <<< 1) + $signed({15'd0, nr_z[22]});
    wire signed [15:0] nr_n = (nr_r >= 0) ? nr_2r - Ls16 : nr_2r + Ls16;
    // final value
    wire signed [15:0] nr_R = (nr_r < 0) ? nr_r + Ls16 : nr_r;
    wire up = (nr_R <<< 1) >= Ls16;
    wire [23:0] Qm = {1'b0, nr_q} + {23'd0, up};
    // CHECK = 1: invalid when L = 0, O = -2^19, or the rounded magnitude leaves the 12-bit range.
    // CHECK = 0: no check (the domain assumption guarantees in_range, so +-Qm[11:0] is exact).
    wire ref_valid = !CHECK || ((L_s != 12'd0) && (O_s != -20'sd524288) && (O_s[19] ? Qm <= 24'd2048 : Qm <= 24'd2047));
    wire [11:0] ref_val = !ref_valid ? 12'd0 : O_s[19] ? 12'd0 - Qm[11:0] : Qm[11:0];

    always @(posedge clk) begin
        init <= 1'b0;
        p_rst_n <= rst_n;
        p_shift <= shift;
        p_result <= result;
        p_fin <= rst_n && cnt == 5'd24;
        p_ref <= ref_val;
        if (!rst_n) cnt <= 5'd0;
        else if (cnt == 5'd0) cnt <= start ? 5'd1 : 5'd0;
        else if (cnt == 5'd24) cnt <= 5'd0;
        else cnt <= cnt + 5'd1;
        if (accept) begin
            O_s <= sum_in; L_s <= denominator;
            nr_r <= 16'sd0; nr_z <= {a_in[18:0], 4'b0}; nr_q <= 23'd0;
        end else if (cnt >= 5'd1 && cnt <= 5'd23) begin
            nr_r <= nr_n; nr_z <= {nr_z[21:0], 1'b0}; nr_q <= {nr_q[21:0], nr_n >= 0};
        end
    end

    // ---- assumptions ----
    always @* begin
        if (init) assume (!rst_n);
        if (!CHECK && accept) assume (in_range(sum_in, denominator));
        if (!LATCH && cnt != 5'd0) assume (denominator == L_s);
    end

    // ---- protocol + value assertions ----
    always @* if (!init) begin
        a_busy: assert (busy == (cnt != 5'd0));
        a_done: assert (done == p_fin);
        if (!p_rst_n) a_reset: assert (result == 12'sd0 && !done);
        else if (p_fin) a_value: assert (result == p_ref);
        else a_hold: assert (result == (p_shift ? {p_result[10:0], 1'b0} : p_result));
    end

    // ---- WB lemmas ----
    (* keep *) wire [1:0] w_state;
    (* keep *) wire [4:0] w_step;
    (* keep *) wire [22:0] w_q;
    (* keep *) wire [11:0] w_r;
    (* keep *) wire w_neg, w_inv;
    (* keep *) wire [11:0] w_div;
    wire [4:0] nb = (cnt == 5'd24) ? 5'd23 : cnt - 5'd1;      // bits consumed so far
    wire [23:0] qmask = (24'd1 << nb) - 24'd1;
    always @* if (WB && !init) begin
        inv_cnt: assert (cnt <= 5'd24);
        inv_idle: assert ((w_state == 2'd0) == (cnt == 5'd0));
        if (cnt >= 5'd1 && cnt <= 5'd23) inv_div: assert (w_state == 2'd1 && w_step == cnt - 5'd1);
        if (cnt == 5'd24) inv_round: assert (w_state == 2'd2);
        if (cnt != 5'd0) begin
            if (!CHECK) inv_dom: assert (in_range(O_s, L_s));
            inv_neg: assert (w_neg == O_s[19]);
            inv_divisor: assert (w_div == L_s);
            // RELAX_INV = 1 (for a mutant that drops the L = 0 term of invalid_r): only checked for L != 0
            if (CHECK && (!RELAX_INV || L_s != 12'd0)) inv_invalid: assert (w_inv == (L_s == 12'd0 || O_s == -20'sd524288));
            // divisor 0: every restoring step subtracts, so the quotient bits so far are all ones
            if (L_s == 12'd0) inv_q0: assert ((w_q & qmask[22:0]) == qmask[22:0]);
            inv_zq: assert ((nr_z & qmask[22:0]) == 23'd0 && (nr_q & ~qmask[22:0]) == 23'd0);
            inv_zz: assert (nr_z == ({a_s[18:0], 4'b0} << nb));
            if (L_s != 12'd0) begin
                inv_rng: assert (nr_r >= -Ls16 && nr_r < Ls16);
                inv_q: assert (w_q == (nr_z | nr_q));
                inv_r: assert ($signed({4'd0, w_r}) == ((nr_r < 0) ? nr_r + Ls16 : nr_r));
            end
        end
    end

    // ---- EDGE = 1: multiplicative bracket on a table of operand pairs (BMC only) ----
    generate if (EDGE) begin : g_edge
        (* anyconst *) reg [6:0] idx;
        reg signed [19:0] to; reg [11:0] tl;
        always @* begin
            case (idx)
            `include "edge_table.vh"
            default: begin to = 20'sd0; tl = 12'd1; end
            endcase
        end
        always @* begin
            assume (idx < `EDGE_N);
            if (accept) assume (sum_in == to && denominator == tl);
        end
        wire neg = O_s[19];
        wire signed [31:0] twoZ = $signed({11'd0, a_s}) * 32;
        wire signed [31:0] Lw = $signed({20'd0, L_s});
        wire signed [31:0] rW = {{20{result[11]}}, result};
        wire signed [31:0] Qw = neg ? -rW : rW;
        wire sign_ok = neg ? !(result > 0) : !(result < 0);
        wire bracket = sign_ok && ((2 * Qw - 1) * Lw <= twoZ) && (twoZ < (2 * Qw + 1) * Lw);
        reg ref_valid_p = 1'b0;
        always @(posedge clk) ref_valid_p <= ref_valid;
        always @* if (!init && p_rst_n && p_fin) begin
            if (ref_valid_p) e_bracket: assert (bracket);
            else if (CHECK) e_invalid0: assert (result == 12'sd0);
        end
        always @* if (!init && p_rst_n && p_fin) c_edge_done: cover (1'b1);
    end endgenerate

    // ---- covers ----
    always @* if (!init && p_rst_n && p_fin) begin
        c_tie_pos: cover (O_s == 20'sd1 && L_s == 12'd32 && result == 12'sd1);
        c_tie_neg: cover (O_s == -20'sd1 && L_s == 12'd32 && result == -12'sd1);
        c_min: cover (result == -12'sd2048);
        c_max: cover (result == 12'sd2047);
        c_negzero: cover (O_s[19] && result == 12'sd0);
        c_bigL: cover (L_s == 12'd4095 && result != 12'sd0);
        c_invalid: cover (!ref_valid);
    end
    always @* if (!init) c_b2b: cover (done && accept);
endmodule
`default_nettype wire
