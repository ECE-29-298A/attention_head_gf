// Second-simulator (Icarus, 4-state) check for exp_lut REGISTERED = 1: applies golden-model
// vectors "rst_n start D shift done W" (hex; W = x while the model does not know W, i.e.
// before the first reset or start), one line per clock cycle, and compares done and W after
// the rising edge with !== (an X or Z bit is a mismatch wherever the file has a value).
// done is compared on every cycle. Also checks every cycle that W and done do not change
// when the inputs change with clk low, nor at the falling edge. Plusarg +VEC=<file>.
// Compile with -DGATE for a gate-level netlist (no parameter).
`timescale 1ns/1ps
module tb_vectors;
    reg         clk = 1'b0, rst_n = 1'b1, start = 1'b0;
    reg  [21:0] D = 22'd0;
    reg  [3:0]  shift = 4'd0;
    wire        done;
    wire [7:0]  W;
`ifdef GATE
    exp_lut dut (.clk(clk), .rst_n(rst_n), .start(start), .D(D), .shift(shift), .done(done), .W(W));
`else
    exp_lut #(.REGISTERED(1)) dut (.clk(clk), .rst_n(rst_n), .start(start), .D(D), .shift(shift), .done(done), .W(W));
`endif

    integer fd, rc, n_vec, n_chk, n_bad, r_in, s_in, dn_in;
    reg [1023:0] fname;
    reg [8*128-1:0] line;
    reg [8*8-1:0] wtxt;
    reg [7:0] e, w_before;
    reg d_before, known;
    initial begin
        n_vec = 0; n_chk = 0; n_bad = 0;
        if (!$value$plusargs("VEC=%s", fname)) begin
            $display("RESULT sim=icarus vectors=0 checked=0 mismatches=1 (no +VEC)");
            $finish_and_return(1);
        end
        fd = $fopen(fname, "r");
        if (fd == 0) begin
            $display("RESULT sim=icarus vectors=0 checked=0 mismatches=1 (cannot open)");
            $finish_and_return(1);
        end
        #5;
        while (!$feof(fd)) begin
            rc = $fgets(line, fd);
            if (rc > 0 && line[8*rc-1 -: 8] != "#") begin
                rc = $sscanf(line, "%d %d %h %h %d %s", r_in, s_in, D, shift, dn_in, wtxt);
                if (rc == 6) begin
                    known = (wtxt[7:0] != "x");
                    if (known) rc = $sscanf(wtxt, "%h", e);
                    w_before = W; d_before = done;
                    rst_n = r_in[0]; start = s_in[0];
                    #4;                                   // inputs settled, clk still low
                    if (W !== w_before || done !== d_before) begin
                        n_bad = n_bad + 1;
                        if (n_bad <= 20) $display("MISMATCH(comb-path) vec=%0d W=%h done=%b", n_vec, W, done);
                    end
                    clk = 1'b1;
                    #1;
                    n_vec = n_vec + 1;
                    if (done !== dn_in[0] || (known && W !== e)) begin
                        n_bad = n_bad + 1;
                        if (n_bad <= 20)
                            $display("MISMATCH vec=%0d rst_n=%b start=%b D=%h shift=%h done=%b W=%h exp_done=%0d exp_W=%0s",
                                     n_vec, rst_n, start, D, shift, done, W, dn_in, wtxt);
                    end
                    if (known) n_chk = n_chk + 1;
                    w_before = W; d_before = done;
                    #4 clk = 1'b0;
                    #1;
                    if (W !== w_before || done !== d_before) begin
                        n_bad = n_bad + 1;
                        if (n_bad <= 20) $display("MISMATCH(negedge) vec=%0d", n_vec);
                    end
                end
            end
        end
        $fclose(fd);
        $display("RESULT sim=icarus vectors=%0d checked=%0d mismatches=%0d", n_vec, n_chk, n_bad);
        if (n_bad != 0 || n_vec == 0) $finish_and_return(1);
        $finish;
    end
endmodule
