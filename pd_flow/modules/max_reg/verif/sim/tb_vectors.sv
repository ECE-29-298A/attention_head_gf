// Second-simulator (Icarus, 4-state) check: applies golden-model vectors
// "first en S_in M" (hex; M = x while the model does not know M) to max_reg, one line per
// clock cycle, and compares M after the rising edge with the file using !== (an X or Z bit
// in M is a mismatch wherever the file has a value). Also checks every cycle that M does
// not change when the inputs change with clk low (registered output). Plusarg +VEC=<file>.
// Before the first load M is X in this simulator (no reset, no initial value); those cycles
// are not compared.
`timescale 1ns/1ps
module tb_vectors;
    reg         clk = 1'b0, first = 1'b0, en = 1'b0;
    reg  [21:0] S_in = 22'd0, e, m_before;
    wire [21:0] M;
    max_reg dut (.clk(clk), .first(first), .en(en), .S_in(S_in), .M(M));

    integer fd, rc, n_vec, n_chk, n_bad, f_in, e_in;
    reg [1023:0] fname;
    reg [8*128-1:0] line;
    reg [8*8-1:0] mtxt;
    reg known;
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
                rc = $sscanf(line, "%d %d %h %s", f_in, e_in, S_in, mtxt);
                if (rc == 4) begin
                    known = (mtxt[7:0] != "x");
                    if (known) rc = $sscanf(mtxt, "%h", e);
                    m_before = M;
                    first = f_in[0]; en = e_in[0];
                    #4;                                   // inputs settled, clk still low
                    if (M !== m_before) begin
                        n_bad = n_bad + 1;
                        if (n_bad <= 20) $display("MISMATCH(comb-path) vec=%0d M=%h before=%h", n_vec, M, m_before);
                    end
                    clk = 1'b1;
                    #1;
                    n_vec = n_vec + 1;
                    if (known) begin
                        n_chk = n_chk + 1;
                        if (M !== e) begin
                            n_bad = n_bad + 1;
                            if (n_bad <= 20)
                                $display("MISMATCH vec=%0d first=%b en=%b S_in=%h M=%h exp=%h", n_vec, first, en, S_in, M, e);
                        end
                    end
                    #4 clk = 1'b0;
                    #1;
                end
            end
        end
        $fclose(fd);
        $display("RESULT sim=icarus vectors=%0d checked=%0d mismatches=%0d", n_vec, n_chk, n_bad);
        if (n_bad != 0 || n_vec == 0) $finish_and_return(1);
        $finish;
    end
endmodule
