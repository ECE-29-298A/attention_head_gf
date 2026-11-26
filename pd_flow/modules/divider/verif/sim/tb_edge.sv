// edge_00 / edge_11 item: directed edge cases plus fixed-seed spot checks (user decision D9b),
// Icarus 4-state. Not exhaustive. Points come from edges.txt (model/golden_model.py edges):
// "S L e00 e11 class". -DP11 selects LATCH_DENOMINATOR = CHECK_INVALID = 1 (else 0/0, where
// points outside the caller's domain, e00 = x, are skipped); -DGATE instantiates a netlist.
//
// Every cycle the TB's own reference (SPEC R1-R11, written from the SPEC, not from the RTL)
// predicts busy, done and result, and the DUT is compared with !== (X or Z fails) right after
// the rising edge and again after the falling edge (registered outputs). Around the points:
//   - the accept edge takes S, L; during the 24 busy edges sum_in is random (must be ignored);
//     at 1/1 the denominator is random too (latched), at 0/0 it is held (caller guarantee A1);
//   - starts while busy (ignored), shifts while busy (shift the held result), a shift on the
//     completion edge (the completion wins), back-to-back starts in the done cycle, idle gaps
//     with shifts, a reset in the middle of a division (abort; reset wins over start and
//     shift), and a 12-bit serial shift-out MSB first on result[11].
`timescale 1ns/1ps
`default_nettype none
module tb_edge;
`ifdef P11
    localparam LD = 1, CI = 1;
`else
    localparam LD = 0, CI = 0;
`endif
    reg clk = 1'b0, rst_n = 1'b0, start = 1'b0, shift = 1'b0;
    reg [19:0] sum_in = 20'd0;
    reg [11:0] denominator = 12'd0;
    wire busy, done;
    wire [11:0] result;
`ifdef GATE
    divider dut (.clk(clk), .rst_n(rst_n), .start(start), .sum_in(sum_in), .denominator(denominator),
                 .shift(shift), .busy(busy), .done(done), .result(result));
`else
    divider #(.LATCH_DENOMINATOR(LD), .CHECK_INVALID(CI)) dut (.clk(clk), .rst_n(rst_n),
                 .start(start), .sum_in(sum_in), .denominator(denominator), .shift(shift),
                 .busy(busy), .done(done), .result(result));
`endif

    integer cnt = 0;                 // reference: edges since the accept, 0 = idle
    reg [11:0] eres = 12'd0, E = 12'd0;
    reg edone = 1'b0;
    integer errs = 0, checks = 0, cycles = 0, seed = 32'h5EED;
    integer n_pts = 0, n_skip = 0, n_sb = 0, n_shb = 0, n_shd = 0, n_ab = 0, n_ser = 0, n_b2b = 0, n_idle = 0;

    task check(input [8*8-1:0] when);
        begin
            checks = checks + 1;
            if (busy !== (cnt != 0) || done !== edone || result !== eres) begin
                errs = errs + 1;
                if (errs <= 10)
                    $display("MISMATCH %0s t=%0t cnt=%0d busy=%b(exp %b) done=%b(exp %b) result=%h(exp %h)",
                             when, $time, cnt, busy, cnt != 0, done, edone, result, eres);
            end
        end
    endtask

    // One clock: drive the inputs (just after a falling edge), predict the rising edge, check.
    task cyc(input r, input st, input sh, input [19:0] s, input [11:0] l, input [11:0] e_acc);
        integer cn;
        reg [11:0] rn;
        reg dn;
        begin
            rst_n = r; start = st; shift = sh; sum_in = s; denominator = l;
            if (!r) begin cn = 0; rn = 12'd0; dn = 1'b0; end
            else begin
                dn = cnt == 24;
                rn = cnt == 24 ? E : sh ? {eres[10:0], 1'b0} : eres;
                if (cnt == 0) cn = st ? 1 : 0;
                else cn = cnt == 24 ? 0 : cnt + 1;
                if (cnt == 0 && st) E = e_acc;
            end
            #5 clk = 1'b1;
            #1 cnt = cn; eres = rn; edone = dn;
            check("rise");
            #4 clk = 1'b0;
            #1 check("fall");
            cycles = cycles + 1;
        end
    endtask

    function [19:0] r20; input dummy; r20 = $random(seed); endfunction
    function [11:0] r12; input dummy; r12 = $random(seed); endfunction
    function rb; input [7:0] m; rb = (($random(seed) & 32'hff) & m) == 0; endfunction

    integer fd, rc, s, l, e0, e1, e, mode, c, k, att;
    reg [8*16-1:0] e0s, cls;
    reg [8*256-1:0] fname;
    reg [11:0] ldrv;
    reg sh, st;
    initial begin
        if (!$value$plusargs("EDGES=%s", fname)) begin
            $display("RESULT sim=icarus points=0 mismatches=1 (missing +EDGES)"); $finish_and_return(1);
        end
        fd = $fopen(fname, "r");
        if (fd == 0) begin $display("RESULT sim=icarus points=0 mismatches=1 (cannot open)"); $finish_and_return(1); end
        #1;
        cyc(1'b0, 1'b0, 1'b0, r20(0), r12(0), 12'd0);   // reset
        cyc(1'b0, 1'b1, 1'b1, r20(0), r12(0), 12'd0);   // reset wins over start and shift
        while (!$feof(fd)) begin
            rc = $fscanf(fd, "%d %d %s %d %s\n", s, l, e0s, e1, cls);
            if (rc == 5) begin
                if (CI == 0 && e0s == "x") n_skip = n_skip + 1;
                else begin
                    if (CI == 0) rc = $sscanf(e0s, "%d", e0);
                    e = CI ? e1 : e0;
                    n_pts = n_pts + 1;
                    mode = n_pts;
                    // idle gap with random shifts, or back-to-back (accept in the done cycle)
                    if (mode % 4 != 0)
                        for (k = 0; k < mode % 3; k = k + 1) begin
                            cyc(1'b1, 1'b0, rb(8'h1), r20(0), r12(0), 12'd0); n_idle = n_idle + 1;
                        end
                    for (att = 0; att < 2; att = att + 1) begin
                        if (edone) n_b2b = n_b2b + 1;
                        cyc(1'b1, 1'b1, mode % 5 == 0, s[19:0], l[11:0], e[11:0]);   // accept
                        for (c = 1; c <= 24; c = c + 1) begin
                            if (att == 0 && mode % 29 == 3 && c == 10) begin
                                cyc(1'b0, 1'b1, 1'b1, r20(0), r12(0), 12'd0);         // abort
                                n_ab = n_ab + 1;
                                c = 99;
                            end else begin
                                st = mode % 7 == 1 && rb(8'h3);
                                sh = c == 24 ? mode % 6 == 3 : mode % 5 == 2 && rb(8'h1);
                                if (st) n_sb = n_sb + 1;
                                if (sh && c < 24) n_shb = n_shb + 1;
                                if (sh && c == 24) n_shd = n_shd + 1;
                                ldrv = LD ? r12(0) : l[11:0];
                                cyc(1'b1, st, sh, r20(0), ldrv, 12'd0);
                            end
                        end
                        if (c < 99) att = 2;            // completed without abort
                    end
                    if (mode % 10 == 7) begin           // serial shift-out, MSB first
                        n_ser = n_ser + 1;
                        for (k = 0; k < 12; k = k + 1) begin
                            if (result[11] !== E[11 - k]) begin
                                errs = errs + 1;
                                if (errs <= 10) $display("MISMATCH serial bit %0d of %h: %b", k, E, result[11]);
                            end
                            cyc(1'b1, 1'b0, 1'b1, r20(0), r12(0), 12'd0);
                        end
                    end
                end
            end
        end
        $display("RESULT sim=icarus cfg=%0d%0d points=%0d skipped=%0d cycles=%0d checks=%0d start_busy=%0d shift_busy=%0d shift_done=%0d aborts=%0d serial=%0d b2b=%0d idle=%0d mismatches=%0d",
                 LD, CI, n_pts, n_skip, cycles, checks, n_sb, n_shb, n_shd, n_ab, n_ser, n_b2b, n_idle, errs);
        if (errs != 0 || n_pts == 0) $finish_and_return(1);
        $finish;
    end
endmodule
`default_nettype wire
