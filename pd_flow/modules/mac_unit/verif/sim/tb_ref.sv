// refcheck item: the formal reference formal/ref_mac_next.v (used by fv_spec_*) against the
// Python model (model/golden_model.py next_state) on edge and random points (refpoints.txt:
// "inputs... S L O0 S_n L_n tail_n", hex). Two independent writings of SPEC R1-R12.
`timescale 1ns/1ps
`default_nettype none
module tb_ref;
    reg am, load, sub, se, first, ae, sel0;
    reg [21:0] M, S;
    reg [7:0] qi, ki, W, v;
    reg [2:0] bs;
    reg [11:0] L;
    reg [19:0] O0;
    wire [21:0] S_n;
    wire [11:0] L_n;
    wire [19:0] tail_n;
    ref_mac_next ref0 (.accum_mode(am), .load(load), .subtract(sub), .M(M), .score_en(se),
        .qi(qi), .ki(ki), .first(first), .accum_en(ae), .W(W), .sel_zero(sel0), .v(v),
        .bit_sel(bs), .S(S), .L(L), .O0(O0), .S_n(S_n), .L_n(L_n), .tail_n(tail_n));
    integer fd, r, n = 0, errs = 0;
    reg [31:0] f_am, f_load, f_sub, f_M, f_se, f_qi, f_ki, f_first, f_ae, f_W, f_sel, f_v, f_bs;
    reg [31:0] fS, fL, fO, eS, eL, eT;
    reg [8*256-1:0] path;
    initial begin
        if (!$value$plusargs("POINTS=%s", path)) path = "refpoints.txt";
        fd = $fopen(path, "r");
        if (fd == 0) begin $display("RESULT refcheck error=cannot-open"); $fatal(1); end
        while (!$feof(fd)) begin
            r = $fscanf(fd, "%h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h\n",
                        f_am, f_load, f_sub, f_M, f_se, f_qi, f_ki, f_first, f_ae, f_W, f_sel, f_v, f_bs,
                        fS, fL, fO, eS, eL, eT);
            if (r == 19) begin
                am = f_am[0]; load = f_load[0]; sub = f_sub[0]; M = f_M[21:0]; se = f_se[0];
                qi = f_qi[7:0]; ki = f_ki[7:0]; first = f_first[0]; ae = f_ae[0]; W = f_W[7:0];
                sel0 = f_sel == 0; v = f_v[7:0]; bs = f_bs[2:0]; S = fS[21:0]; L = fL[11:0]; O0 = fO[19:0];
                #1;
                n = n + 1;
                if (S_n !== eS[21:0] || L_n !== eL[11:0] || tail_n !== eT[19:0]) begin
                    errs = errs + 1;
                    if (errs <= 10) $display("MISMATCH point=%0d S_n=%h(exp %h) L_n=%h(exp %h) tail_n=%h(exp %h)",
                                             n, S_n, eS[21:0], L_n, eL[11:0], tail_n, eT[19:0]);
                end
            end else if (r > 0) begin
                errs = errs + 1; $display("MALFORMED point after %0d", n);
            end
        end
        $display("RESULT refcheck points=%0d errors=%0d", n, errs);
        if (errs != 0) $fatal(1);
        $finish;
    end
endmodule
// restore the default for the files that follow (the PDK cell models use implicit nets)
`default_nettype wire
