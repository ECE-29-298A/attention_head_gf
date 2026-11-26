// Second-simulator (Icarus, 4-state) edge-case and spot check of exp_lut against the golden
// model's edge file "D shift W class" (golden_model.py edges). Comparisons use !==, so an X or
// Z bit on W or done is a mismatch (this is the contract's X check, SPEC section 7).
// Plusarg +EDGES=<file>. Compile with -DREG=0 or -DREG=1 (the configuration under test) and,
// for a gate-level netlist (no parameter), -DGATE.
//   REG=0: each point applied with pseudo-random clk, rst_n, start (must not change W);
//          done must equal start; then D+1 at the same shift: W(D+1) <= W(D).
//   REG=1: each point loaded with start = 1 (W and done checked after the rising edge),
//          then D+1 loaded (monotonicity); a hold cycle with other inputs after every 16th
//          point and a reset (with start = 1) every 1,024 points; W and done must not change
//          while clk is low or at the falling edge.
// Targeted checks on every point: R4 (D >= 2^20 gives W = 0) and R3 (W = 0 exactly when
// D' >= 25, with D' = (D + 2^(shift-1)) >> shift computed here on 23 bits).
`timescale 1ns/1ps
module tb_edge;
    reg         clk = 1'b0, rst_n = 1'b1, start = 1'b0;
    reg  [21:0] D = 22'd0;
    reg  [3:0]  shift = 4'd0;
    wire        done;
    wire [7:0]  W;
`ifdef GATE
    exp_lut dut (.clk(clk), .rst_n(rst_n), .start(start), .D(D), .shift(shift), .done(done), .W(W));
`else
    exp_lut #(.REGISTERED(`REG)) dut (.clk(clk), .rst_n(rst_n), .start(start), .D(D), .shift(shift), .done(done), .W(W));
`endif

    integer fd, rc, n_pts, n_bad, n_cyc, n_r3, n_r4, n_mono, lfsr, ew, s_in;
    reg [21:0] d_in;
    reg [8*32-1:0] cls;
    reg [1023:0] fname;
    reg [7:0] w_before, w0;
    reg done_before;
    reg [22:0] dp;

    task automatic bad(input [255:0] what, input integer exp_w);
        begin
            n_bad = n_bad + 1;
            if (n_bad <= 20)
                $display("MISMATCH(%0s) D=%h shift=%0d rst_n=%b start=%b W=%b done=%b exp_W=%0d",
                         what, D, shift, rst_n, start, W, done, exp_w);
        end
    endtask

    task automatic targeted(input [21:0] dv, input [3:0] sv, input [7:0] wv);
        begin
            dp = ({1'b0, dv} + ((sv == 4'd0) ? 23'd0 : (23'd1 << (sv - 4'd1)))) >> sv;
            n_r3 = n_r3 + 1;
            if ((wv === 8'd0) != (dp >= 23'd25)) bad("R3", -1);
            if (dv >= 22'h100000) begin
                n_r4 = n_r4 + 1;
                if (wv !== 8'd0) bad("R4", 0);
            end
        end
    endtask

    // one REGISTERED=1 clock cycle (inputs applied with clk low, rising edge, falling edge)
    task automatic cyc(input r, input st, input [21:0] dv, input [3:0] sv, input integer exp_d, input integer exp_w);
        begin
            w_before = W; done_before = done;
            rst_n = r; start = st; D = dv; shift = sv;
            #4;
            if (W !== w_before || done !== done_before) bad("comb-path", -1);
            clk = 1'b1;
            #1;
            n_cyc = n_cyc + 1;
            if (done !== exp_d[0]) bad("done", exp_w);
            if (exp_w >= 0 && W !== exp_w[7:0]) bad("W", exp_w);
            w_before = W; done_before = done;
            #4 clk = 1'b0;
            #1;
            if (W !== w_before || done !== done_before) bad("negedge", -1);
        end
    endtask

    initial begin
        n_pts = 0; n_bad = 0; n_cyc = 0; n_r3 = 0; n_r4 = 0; n_mono = 0; lfsr = 32'h1234567;
        if (!$value$plusargs("EDGES=%s", fname)) begin
            $display("RESULT sim=icarus points=0 mismatches=1 (missing +EDGES)");
            $finish_and_return(1);
        end
        fd = $fopen(fname, "r");
        if (fd == 0) begin
            $display("RESULT sim=icarus points=0 mismatches=1 (cannot open)");
            $finish_and_return(1);
        end
        #5;
        if (`REG != 0) cyc(1'b0, 1'b1, 22'h3fffff, 4'd0, 0, 0);
        while (!$feof(fd)) begin
            rc = $fscanf(fd, "%h %d %d %s\n", d_in, s_in, ew, cls);
            if (rc == 4) begin
                n_pts = n_pts + 1;
                if (`REG == 0) begin
                    lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
                    clk = lfsr[3]; rst_n = lfsr[7]; start = lfsr[11];
                    D = d_in; shift = s_in;
                    #1;
                    if (W !== ew[7:0] || done !== start) bad("edge0", ew);
                    w0 = W;
                    targeted(d_in, s_in, w0);
                    if (d_in != 22'h3fffff) begin
                        lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
                        clk = lfsr[3]; rst_n = lfsr[7]; start = lfsr[11];
                        D = d_in + 22'd1;
                        #1;
                        n_mono = n_mono + 1;
                        if (!(W <= w0) || ^W === 1'bx || done !== start) bad("monotone", w0);
                    end
                end else begin
                    cyc(1'b1, 1'b1, d_in, s_in, 1, ew);
                    w0 = W;
                    targeted(d_in, s_in, w0);
                    if (d_in != 22'h3fffff) begin
                        cyc(1'b1, 1'b1, d_in + 22'd1, s_in, 1, -1);
                        n_mono = n_mono + 1;
                        if (!(W <= w0) || ^W === 1'bx) bad("monotone", w0);
                    end
                    lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
                    if ((n_pts % 16) == 0) cyc(1'b1, 1'b0, lfsr[21:0] ^ d_in, lfsr[25:22], 0, W);
                    if ((n_pts % 1024) == 0) cyc(1'b0, 1'b1, d_in, s_in, 0, 0);
                end
            end
        end
        $fclose(fd);
        $display("RESULT sim=icarus reg=%0d points=%0d r3_checked=%0d r4_checked=%0d mono_checked=%0d cycles=%0d mismatches=%0d",
                 `REG, n_pts, n_r3, n_r4, n_mono, n_cyc, n_bad);
        if (n_bad != 0 || n_pts == 0) $finish_and_return(1);
        $finish;
    end
endmodule
