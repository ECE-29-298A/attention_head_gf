// EQY harness with observer ports (Agent 3, divider), identical on both sides. Power-on reset in
// cycle 0 (boot, init 1); every port, observers included, compared from cycle 1 on.
module eqtop #(parameter LD = 1, parameter CI = 1) (
    input  wire clk, input wire rst_n, input wire start,
    input  wire signed [19:0] sum_in, input wire [11:0] denominator, input wire shift,
    output wire busy_o, output wire done_o, output wire [11:0] result_o,
    output wire lg_o, lc_o, output wire [4:0] ph_o, output wire [18:0] dq_o,
    output wire [11:0] rm_o, dv_o, output wire ng_o, iv_o, sn_o
);
    reg boot = 1'b1;
    always @(posedge clk) boot <= 1'b0;
    wire busy, done, lg, lc, ng, iv, sn;
    wire signed [11:0] result;
    wire [4:0] ph; wire [18:0] dq; wire [11:0] rm, dv;
    divider #(.LATCH_DENOMINATOR(LD), .CHECK_INVALID(CI)) u (
        .clk(clk), .rst_n(rst_n & ~boot), .start(start), .sum_in(sum_in), .denominator(denominator),
        .shift(shift), .obs_lg(lg), .obs_lc(lc), .obs_ph(ph), .obs_dq(dq), .obs_rm(rm), .obs_dv(dv),
        .obs_ng(ng), .obs_iv(iv), .obs_sn(sn), .busy(busy), .done(done), .result(result));
    assign busy_o = ~boot & busy;
    assign done_o = ~boot & done;
    assign result_o = {12{~boot}} & result;
    assign lg_o = boot | lg;
    assign lc_o = boot | lc;
    assign ph_o = {5{~boot}} & ph;
    assign dq_o = {19{~boot}} & dq;
    assign rm_o = {12{~boot}} & rm;
    assign dv_o = {12{~boot}} & dv;
    assign ng_o = ~boot & ng;
    assign iv_o = ~boot & iv;
    assign sn_o = ~boot & sn;
endmodule
