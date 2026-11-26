// Second-simulator (Icarus, 4-state) exhaustive check of exp_lut against the golden model's
// interval file "shift lo hi W" (golden_model.py intervals). Comparisons use !==, so an X or
// Z bit on W or done is a mismatch. Plusargs: +IV=<file> +SLO=<a> +SHI=<b> (shift range a..b).
// Compile with -DREG=0 or -DREG=1 (the configuration under test) and, for a gate-level
// netlist (no parameter), -DGATE.
//   REG=0: every D for each shift in a..b; clk, rst_n and start take pseudo-random values at
//          every point and must not change W; done must equal start.
//   REG=1: every D for each shift in a..b is loaded with start = 1 (W and done checked after the
//          rising edge), back to back (done stays 1); after every 16th load one hold cycle
//          with start = 0 and other D, shift (W holds, done = 0); a reset (with start = 1) before each shift and every 4,096 loads; W and
//          done must not change while clk is low or at the falling edge.
`timescale 1ns/1ps
module tb_exh;
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

    integer fd, rc, n_iv, slo, shi, s, i, n_pts, n_bad, n_cyc;
    integer iv_s [0:1023];
    integer iv_lo[0:1023];
    integer iv_hi[0:1023];
    integer iv_w [0:1023];
    integer d, ew, lfsr;
    reg [1023:0] fname;
    reg [7:0] w_before;
    reg done_before;

    task automatic bad(input [255:0] what, input integer exp_w, input integer exp_d);
        begin
            n_bad = n_bad + 1;
            if (n_bad <= 20)
                $display("MISMATCH(%0s) D=%h shift=%0d rst_n=%b start=%b clk=%b W=%b done=%b exp_W=%0d exp_done=%0d",
                         what, D, shift, rst_n, start, clk, W, done, exp_w, exp_d);
        end
    endtask

    // one REGISTERED=1 clock cycle (inputs applied with clk low, rising edge, falling edge)
    task automatic cyc(input r, input st, input [21:0] dv, input [3:0] sv, input integer exp_d, input integer exp_w);
        begin
            w_before = W; done_before = done;
            rst_n = r; start = st; D = dv; shift = sv;
            #4;
            if (W !== w_before || done !== done_before) bad("comb-path", -1, -1);
            clk = 1'b1;
            #1;
            n_cyc = n_cyc + 1;
            if (done !== exp_d[0]) bad("done", exp_w, exp_d);
            if (exp_w >= 0 && W !== exp_w[7:0]) bad("W", exp_w, exp_d);
            w_before = W; done_before = done;
            #4 clk = 1'b0;
            #1;
            if (W !== w_before || done !== done_before) bad("negedge", -1, -1);
        end
    endtask

    initial begin
        n_iv = 0; n_pts = 0; n_bad = 0; n_cyc = 0; lfsr = 32'h1234567;
        if (!$value$plusargs("IV=%s", fname) || !$value$plusargs("SLO=%d", slo) || !$value$plusargs("SHI=%d", shi)) begin
            $display("RESULT sim=icarus points=0 mismatches=1 (missing plusargs)");
            $finish_and_return(1);
        end
        fd = $fopen(fname, "r");
        if (fd == 0) begin
            $display("RESULT sim=icarus points=0 mismatches=1 (cannot open)");
            $finish_and_return(1);
        end
        while (!$feof(fd)) begin
            rc = $fscanf(fd, "%d %d %d %d\n", iv_s[n_iv], iv_lo[n_iv], iv_hi[n_iv], iv_w[n_iv]);
            if (rc == 4) n_iv = n_iv + 1;
        end
        $fclose(fd);
        #5;
        for (i = 0; i < n_iv; i = i + 1) begin
            s = iv_s[i];
            if (s >= slo && s <= shi) begin
                if (`REG == 0) begin
                    for (d = iv_lo[i]; d <= iv_hi[i]; d = d + 1) begin
                        lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
                        clk = lfsr[3]; rst_n = lfsr[7]; start = lfsr[11];
                        D = d; shift = s;
                        #1;
                        n_pts = n_pts + 1;
                        if (W !== iv_w[i][7:0] || done !== start) bad("exh0", iv_w[i], start);
                    end
                end else begin
                    if (iv_lo[i] == 0) cyc(1'b0, 1'b1, 22'h3fffff, 4'd0, 0, 0);
                    for (d = iv_lo[i]; d <= iv_hi[i]; d = d + 1) begin
                        cyc(1'b1, 1'b1, d, s, 1, iv_w[i]);
                        n_pts = n_pts + 1;
                        lfsr = {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};
                        if ((n_pts % 16) == 0) cyc(1'b1, 1'b0, lfsr[21:0] ^ d, lfsr[25:22], 0, iv_w[i]);
                        if ((n_pts % 4096) == 0) cyc(1'b0, 1'b1, d, s, 0, 0);
                    end
                end
            end
        end
        $display("RESULT sim=icarus reg=%0d shifts=%0d..%0d points=%0d expected=%0d cycles=%0d mismatches=%0d",
                 `REG, slo, shi, n_pts, (shi - slo + 1) * 4194304, n_cyc, n_bad);
        if (n_bad != 0 || n_pts != (shi - slo + 1) * 4194304) $finish_and_return(1);
        $finish;
    end
endmodule
